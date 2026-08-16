"""Exposure-enforcing session router with M3 lifecycle holds."""
from __future__ import annotations

import threading
import uuid

from .errors import (InvalidSessionTransitionError, RouterError,
                     SessionBusyError, SessionNotFoundError, TransportError)
from .journal import SessionJournal
from .models import (HandoffMode, RouteRequest, RouteType, Session,
                     SessionState)
from .policy import RoutePolicy
from .state_machine import validate_transition
from .transports import TCPConnector, UnsupportedConnector


class SessionHandle:
    def __init__(self, router: "Router", session_id: str):
        self.router = router
        self.id = session_id

    @property
    def session(self):
        return self.router.status(self.id)

    def read(self, size=65536):
        return self.router.read(self.id, size)

    def write(self, data):
        return self.router.write(self.id, data)

    def close(self, reason="caller_closed"):
        return self.router.close_session(self.id, reason)


class Router:
    TERMINATION_REASONS = frozenset(("caller_closed", "endpoint_eof", "transport_error",
                                     "handoff_replaced", "parent_closed", "open_failed", "shutdown"))
    def __init__(self, registry, supervisor, state_dir, connectors=None, clock=None,
                 connect_timeout=10.0, id_factory=None):
        self.registry = registry
        self.supervisor = supervisor
        self.policy = RoutePolicy(registry)
        self.journal = SessionJournal(state_dir)
        self.clock = clock or getattr(supervisor, "clock", None)
        self.connect_timeout = connect_timeout
        self.id_factory = id_factory or (lambda: uuid.uuid4().hex)
        self.connectors = {"tcp": TCPConnector(), **(connectors or {})}
        self.sessions: dict[str, Session] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._index_lock = threading.Lock()

    def _now(self):
        if self.clock is None:
            import datetime as dt
            return dt.datetime.now().astimezone().isoformat()
        return self.clock.now().isoformat()

    def list_direct_services(self):
        return self.policy.list_direct_services()

    def authorize_route(self, request, origin_session_id=None):
        self._validate_origin(request, origin_session_id)
        return self.policy.authorize(request)

    def _validate_origin(self, request, origin_session_id):
        if request.route_type != RouteType.VIA_SERVICE:
            return
        if not origin_session_id:
            raise SessionBusyError("via_service route requires an active origin session")
        origin = self._session(origin_session_id)
        with self._locks[origin.id]:
            if origin.state not in (SessionState.ACTIVE, SessionState.HANDING_OFF):
                raise SessionBusyError(f"origin session {origin.id} is not active")
            if origin.target_service != request.origin_service:
                raise SessionBusyError("origin session does not match the claimed origin service")

    def _register(self, request, parent_session_id=None, handoff_mode=None):
        session_id = self.id_factory()
        session = Session(session_id, request.target_service, request.origin_service,
                          RouteType(request.route_type), self._now(), request.terminal,
                          dict(request.caller_metadata), parent_session_id=parent_session_id,
                          handoff_mode=handoff_mode,
                          return_to_origin=handoff_mode == HandoffMode.RETURN_TO_ORIGIN)
        with self._index_lock:
            if session_id in self.sessions:
                raise RouterError(f"duplicate generated session id: {session_id}")
            self.sessions[session_id] = session
            self._locks[session_id] = threading.RLock()
        self._event(session, "created", None, SessionState.CREATED)
        return session

    def _event(self, session, event_type, old, new, reason=None, error=None):
        self.journal.append({"timestamp": self._now(), "session_id": session.id,
                             "target_service": session.target_service,
                             "origin_service": session.origin_service,
                             "event_type": event_type,
                             "old_state": old.value if old else None,
                             "new_state": new.value if new else None,
                             "endpoint_id": session.endpoint.get("id") if session.endpoint else None,
                             "termination_reason": reason,
                             "error": type(error).__name__ if error else None})

    def _transition(self, session, new, event_type, reason=None, error=None):
        old = session.state
        validate_transition(old, new)
        session.state = new
        self._event(session, event_type, old, new, reason, error)

    def open_session(self, request: RouteRequest, *, parent_session_id=None,
                     handoff_mode: HandoffMode | None = None):
        session = self._register(request, parent_session_id, handoff_mode)
        lock = self._locks[session.id]
        with lock:
            try:
                self._transition(session, SessionState.AUTHORIZING, "authorizing")
                self._validate_origin(request, parent_session_id)
                resolution = self.policy.authorize(request)
                session.endpoint = resolution["endpoint"]
                self._transition(session, SessionState.ACQUIRING, "authorized")
                session.lifecycle_session_id = self.supervisor.acquire_session(session.target_service)
                self._transition(session, SessionState.CONNECTING, "lifecycle_acquired")
                endpoint_type = session.endpoint["type"]
                connector = self.connectors.get(endpoint_type, UnsupportedConnector(endpoint_type))
                timeout = float(session.endpoint.get("connect_timeout_seconds", self.connect_timeout))
                session.stream = connector.connect(session.endpoint, timeout)
                self._transition(session, SessionState.ACTIVE, "connected")
                return SessionHandle(self, session.id)
            except Exception as exc:
                if session.stream is not None:
                    try: session.stream.close()
                    except Exception: pass
                self._release_hold(session)
                if session.state != SessionState.FAILED:
                    self._transition(session, SessionState.FAILED, "open_failed", reason="open_failed", error=exc)
                session.termination_reason = "open_failed"
                raise

    def _release_hold(self, session):
        if session.lifecycle_session_id and not session.hold_released:
            self.supervisor.release_session(session.target_service, session.lifecycle_session_id)
            session.hold_released = True

    def close_session(self, session_id, reason="caller_closed"):
        session = self._session(session_id)
        reason = reason if reason in self.TERMINATION_REASONS else "other"
        with self._locks[session.id]:
            if session.state == SessionState.CLOSED:
                return session.to_dict()
            if session.state == SessionState.CLOSING:
                return session.to_dict()
            self._transition(session, SessionState.CLOSING, "closing", reason=reason)
            close_error = None
            try:
                if session.stream is not None:
                    session.stream.close()
            except Exception as exc:
                close_error = exc
            try:
                self._release_hold(session)
            except Exception as exc:
                close_error = close_error or exc
            session.termination_reason = reason
            if close_error:
                self._transition(session, SessionState.FAILED, "close_failed", reason=reason, error=close_error)
                raise RouterError(f"session cleanup failed: {type(close_error).__name__}") from close_error
            self._transition(session, SessionState.CLOSED, "closed", reason=reason)
        self._restore_parent(session)
        return session.to_dict()

    def _restore_parent(self, child):
        if not child.return_to_origin or not child.parent_session_id:
            return
        try:
            parent = self._session(child.parent_session_id)
        except SessionNotFoundError:
            return
        with self._locks[parent.id]:
            if parent.state == SessionState.HANDING_OFF:
                self._transition(parent, SessionState.ACTIVE, "handoff_returned")

    def handoff(self, parent_session_id, target_service_id, return_to_origin=True,
                terminal=None, caller_metadata=None):
        parent = self._session(parent_session_id)
        mode = HandoffMode.RETURN_TO_ORIGIN if return_to_origin else HandoffMode.REPLACE
        with self._locks[parent.id]:
            if parent.state != SessionState.ACTIVE:
                raise SessionBusyError(f"session {parent.id} cannot hand off while {parent.state.value}")
            self._transition(parent, SessionState.HANDING_OFF, "handoff_started")
        request = RouteRequest(target_service_id, RouteType.VIA_SERVICE, parent.target_service,
                               terminal or parent.terminal, caller_metadata or {})
        try:
            child = self.open_session(request, parent_session_id=parent.id, handoff_mode=mode)
        except Exception:
            with self._locks[parent.id]:
                if parent.state == SessionState.HANDING_OFF:
                    self._transition(parent, SessionState.ACTIVE, "handoff_failed")
            raise
        if mode == HandoffMode.REPLACE:
            self.close_session(parent.id, "handoff_replaced")
        return child

    def read(self, session_id, size=65536):
        session = self._session(session_id)
        with self._locks[session.id]:
            if session.state != SessionState.ACTIVE:
                raise SessionBusyError(f"session {session.id} is not active")
            stream = session.stream
        try:
            data = stream.read(size)
        except OSError as exc:
            self.close_session(session.id, "transport_error")
            raise TransportError("stream read failed") from exc
        if data == b"":
            self.close_session(session.id, "endpoint_eof")
        return data

    def write(self, session_id, data):
        session = self._session(session_id)
        with self._locks[session.id]:
            if session.state != SessionState.ACTIVE:
                raise SessionBusyError(f"session {session.id} is not active")
            stream = session.stream
        try:
            return stream.write(data)
        except OSError as exc:
            self.close_session(session.id, "transport_error")
            raise TransportError("stream write failed") from exc

    def _session(self, session_id):
        with self._index_lock:
            try:
                return self.sessions[session_id]
            except KeyError as exc:
                raise SessionNotFoundError(f"unknown session: {session_id}") from exc

    def status(self, session_id):
        session = self._session(session_id)
        with self._locks[session.id]:
            return session.to_dict()

    def list_sessions(self):
        with self._index_lock:
            ids = sorted(self.sessions)
        return [self.status(session_id) for session_id in ids]
