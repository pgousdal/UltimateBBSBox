"""Product-neutral lifecycle orchestration."""
from __future__ import annotations

import datetime as dt
import pathlib
import threading
import uuid

from ubb_registry import Registry

from .clock import SystemClock
from .errors import (DriverError, MaintenanceError, ReadinessTimeoutError,
                     RestartLimitExceededError, ServiceBusyError,
                     ServiceNotFoundError, SupervisorError)
from .models import InstanceState
from .persistence import StateStore
from .scheduler import is_due, parse_timestamp
from .state_machine import LifecycleState, validate_transition


ACTIVE_STATES = {LifecycleState.READY, LifecycleState.RUNNING, LifecycleState.MAINTENANCE}
STALE_STATES = {LifecycleState.STARTING, LifecycleState.READY, LifecycleState.STOPPING}


class Supervisor:
    def __init__(self, registry: Registry, state_dir, driver_resolver=None, clock=None, poll_interval: float = 0.1,
                 runtime_manager=None):
        self.registry = registry
        self.store = StateStore(state_dir)
        self.clock = clock or SystemClock()
        self.poll_interval = poll_interval
        self.runtime_manager = runtime_manager
        if driver_resolver is None:
            if self.runtime_manager is None:
                from ubb_runtime import RuntimeManager
                self.runtime_manager = RuntimeManager(registry, pathlib.Path(state_dir) / "runtime")
            self.driver_resolver = self.runtime_manager.driver_for
        else:
            self.driver_resolver = driver_resolver
        self._locks = {service_id: threading.RLock() for service_id in registry.services}
        self._jobs_running: set[tuple[str, str]] = set()
        self.instances: dict[str, InstanceState] = {}
        for service_id in registry.services:
            loaded = self.store.load(service_id)
            self.instances[service_id] = loaded or InstanceState(service_id, f"{service_id}:shared")
        self._validate_jobs()

    def _service(self, service_id):
        try:
            return self.registry.services[service_id]
        except KeyError as exc:
            raise ServiceNotFoundError(f"unknown service: {service_id}") from exc

    def _declaration(self, service):
        return self.registry.resolve(service.id)

    def _driver(self, service):
        return self.driver_resolver(service)

    def _timestamp(self) -> str:
        return self.clock.now().isoformat()

    def _persist(self, instance):
        self.store.save(instance)

    def _transition(self, instance, new_state, reason, error=None):
        old = instance.state
        validate_transition(old, new_state)
        instance.state = new_state
        event = {"service": instance.service_id, "old_state": old.value, "new_state": new_state.value,
                 "timestamp": self._timestamp(), "reason": reason, "instance_id": instance.instance_id}
        if error:
            event["error"] = str(error)
        self.store.append_event(event)
        self._persist(instance)

    def transition(self, service_id, new_state, reason="explicit"):
        service = self._service(service_id)
        with self._locks[service.id]:
            self._transition(self.instances[service.id], LifecycleState(new_state), reason)

    def _add_hold(self, instance, reason):
        instance.holds[reason] = instance.holds.get(reason, 0) + 1
        instance.idle_deadline = None
        self._persist(instance)

    def _remove_hold(self, instance, reason):
        count = instance.holds.get(reason, 0)
        if count <= 1:
            instance.holds.pop(reason, None)
        else:
            instance.holds[reason] = count - 1
        self._persist(instance)

    def start(self, service_id, reason="admin"):
        service = self._service(service_id)
        with self._locks[service.id]:
            instance = self.instances[service.id]
            if reason == "admin":
                instance.admin_intent = True
                if instance.state == LifecycleState.FAILED:
                    instance.restart_exhausted = False
                    instance.restart_times = []
                if not instance.holds.get("admin"):
                    self._add_hold(instance, "admin")
            elif not instance.holds.get(reason):
                self._add_hold(instance, reason)
            self._ensure_running_locked(service, instance, reason)
            return instance.to_dict()

    def ensure_running(self, service_id, reason="admin"):
        return self.start(service_id, reason)

    def _ensure_running_locked(self, service, instance, reason):
        if instance.state in ACTIVE_STATES:
            return
        if instance.state in (LifecycleState.STARTING, LifecycleState.STOPPING):
            raise ServiceBusyError(f"service {service.id} is {instance.state.value}")
        declaration = self._declaration(service)
        driver = self._driver(service)
        self._transition(instance, LifecycleState.STARTING, reason)
        try:
            driver.start(instance, declaration)
            timeout = float(service.document["lifecycle"].get("startup_timeout_seconds", 60))
            readiness = service.document["lifecycle"].get("readiness", {"type": "process_alive"})
            deadline = self.clock.monotonic() + timeout
            while not driver.is_ready(instance, declaration, readiness):
                if self.clock.monotonic() >= deadline:
                    raise ReadinessTimeoutError(f"{service.id} readiness timed out after {timeout:g}s")
                self.clock.sleep(min(self.poll_interval, max(0, deadline - self.clock.monotonic())))
            self._transition(instance, LifecycleState.READY, reason)
            self._transition(instance, LifecycleState.RUNNING, reason)
            instance.last_start_at = self._timestamp()
            instance.last_failure = None
            instance.next_restart_at = None
            instance.restart_exhausted = False
            self._persist(instance)
        except Exception as exc:
            try:
                if driver.status(instance, declaration).get("alive"):
                    driver.stop(instance, declaration)
            except Exception:
                pass
            self._mark_failed_locked(service, instance, exc, "start_failure")
            self._restart_after_failure_locked(service, instance)
            if instance.state == LifecycleState.FAILED:
                raise

    def stop(self, service_id, force=False, reason="admin"):
        service = self._service(service_id)
        with self._locks[service.id]:
            instance = self.instances[service.id]
            if reason == "admin":
                instance.admin_intent = False
                instance.holds.pop("admin", None)
            if force:
                instance.holds.clear(); instance.sessions.clear()
            if instance.active_holds() and not force:
                raise ServiceBusyError(f"service {service.id} has active holds: {instance.holds}")
            self._stop_locked(service, instance, reason)
            return instance.to_dict()

    def _stop_locked(self, service, instance, reason):
        if instance.state == LifecycleState.STOPPED:
            self._persist(instance); return
        if instance.state == LifecycleState.FAILED:
            self._transition(instance, LifecycleState.STOPPED, reason); return
        if instance.state not in ACTIVE_STATES:
            raise ServiceBusyError(f"cannot stop {service.id} while {instance.state.value}")
        self._transition(instance, LifecycleState.STOPPING, reason)
        try:
            self._driver(service).stop(instance, self._declaration(service))
            self._transition(instance, LifecycleState.STOPPED, reason)
            instance.last_stop_at = self._timestamp(); instance.idle_deadline = None
            self._persist(instance)
        except Exception as exc:
            self._mark_failed_locked(service, instance, exc, "stop_failure")
            raise

    def restart(self, service_id):
        self.stop(service_id, force=True, reason="restart")
        return self.start(service_id, reason="admin")

    def acquire_session(self, service_id):
        service = self._service(service_id)
        with self._locks[service.id]:
            instance = self.instances[service.id]
            if service.document["lifecycle"]["sharing"] == "single_session" and instance.sessions:
                raise ServiceBusyError(f"single_session service {service.id} already has an active session")
            session_id = uuid.uuid4().hex
            instance.sessions[session_id] = self._timestamp()
            self._add_hold(instance, "sessions")
            try:
                self._ensure_running_locked(service, instance, "session")
            except Exception:
                instance.sessions.pop(session_id, None); self._remove_hold(instance, "sessions")
                raise
            return session_id

    def release_session(self, service_id, session_id):
        service = self._service(service_id)
        with self._locks[service.id]:
            instance = self.instances[service.id]
            if session_id not in instance.sessions:
                raise SupervisorError(f"unknown session {session_id} for {service.id}")
            instance.sessions.pop(session_id); self._remove_hold(instance, "sessions")
            self._schedule_idle_locked(service, instance)
            return instance.to_dict()

    def _schedule_idle_locked(self, service, instance):
        lifecycle = service.document["lifecycle"]
        if lifecycle["mode"] != "on_demand" or instance.active_holds() or instance.state != LifecycleState.RUNNING:
            return
        if instance.idle_deadline:
            return
        timeout = int(lifecycle.get("idle_timeout_seconds", 0))
        instance.idle_deadline = (self.clock.now() + dt.timedelta(seconds=timeout)).isoformat()
        self._persist(instance)

    def _mark_failed_locked(self, service, instance, error, reason):
        if instance.state != LifecycleState.FAILED:
            self._transition(instance, LifecycleState.FAILED, reason, error)
        instance.last_failure = str(error)
        self._persist(instance)

    def notify_failure(self, service_id, error="runtime exited"):
        service = self._service(service_id)
        with self._locks[service.id]:
            instance = self.instances[service.id]
            self._mark_failed_locked(service, instance, DriverError(str(error)), "runtime_failure")
            self._restart_after_failure_locked(service, instance)
            return instance.to_dict()

    def _restart_after_failure_locked(self, service, instance):
        lifecycle = service.document["lifecycle"]
        if lifecycle.get("restart", "never") not in ("on_failure", "always"):
            return
        now = self.clock.now()
        window = int(lifecycle.get("restart_window_seconds", 60))
        prior = [item for item in instance.restart_times if parse_timestamp(item) and now - parse_timestamp(item) <= dt.timedelta(seconds=window)]
        instance.restart_times = prior
        maximum = int(lifecycle.get("max_restarts", 3))
        if len(prior) >= maximum:
            instance.last_failure = f"restart limit exhausted ({maximum} in {window}s)"
            instance.restart_exhausted = True
            instance.next_restart_at = None
            instance.holds.pop("recovery", None)
            self._persist(instance)
            raise RestartLimitExceededError(instance.last_failure)
        instance.restart_times.append(now.isoformat())
        instance.restart_exhausted = False
        instance.holds["recovery"] = 1
        backoff = float(lifecycle.get("restart_backoff_seconds", 0))
        instance.next_restart_at = (now + dt.timedelta(seconds=backoff)).isoformat()
        self._persist(instance)
        if backoff == 0:
            self._ensure_running_locked(service, instance, "recovery")
            if instance.state == LifecycleState.RUNNING:
                instance.holds.pop("recovery", None); self._persist(instance)

    def run_maintenance(self, service_id, job_id):
        service = self._service(service_id)
        jobs = {job["name"]: job for job in service.document.get("maintenance", {}).get("jobs", [])}
        if job_id not in jobs:
            raise MaintenanceError(f"unknown maintenance job {job_id!r} for {service.id}")
        key = (service.id, job_id)
        lock = self._locks[service.id]
        with lock:
            if key in self._jobs_running:
                raise ServiceBusyError(f"maintenance job already running: {service.id}/{job_id}")
            self._jobs_running.add(key)
            instance = self.instances[service.id]
            was_active = instance.state in ACTIVE_STATES
            if not was_active and not jobs[job_id].get("wake_if_stopped", True):
                self._jobs_running.discard(key)
                raise MaintenanceError(f"maintenance job {service.id}/{job_id} is not allowed to wake a stopped service")
            self._add_hold(instance, "maintenance")
            try:
                self._ensure_running_locked(service, instance, "maintenance")
                self._transition(instance, LifecycleState.MAINTENANCE, f"maintenance:{job_id}")
            except Exception:
                self._remove_hold(instance, "maintenance"); self._jobs_running.discard(key)
                raise
        error = None
        try:
            result = self._driver(service).run_maintenance(instance, self._declaration(service), jobs[job_id])
        except Exception as exc:
            result = {"ok": False, "error": str(exc)}; error = exc
        with lock:
            timestamp = self._timestamp()
            instance.maintenance_results[job_id] = {"timestamp": timestamp, **result}
            instance.schedule_last_run[job_id] = timestamp
            if error:
                self._mark_failed_locked(service, instance, error, f"maintenance_failure:{job_id}")
            else:
                self._transition(instance, LifecycleState.RUNNING, f"maintenance_complete:{job_id}")
            self._remove_hold(instance, "maintenance")
            self._jobs_running.discard(key)
            if not error and not was_active and jobs[job_id].get("shutdown_after", True) and not instance.active_holds():
                self._stop_locked(service, instance, f"maintenance_complete:{job_id}")
            elif not error:
                self._schedule_idle_locked(service, instance)
            if error:
                self._restart_after_failure_locked(service, instance)
                raise MaintenanceError(f"maintenance {service.id}/{job_id} failed: {error}") from error
            return result

    def tick(self):
        self.reconcile()
        now = self.clock.now()
        due = []
        for service in self.registry.services.values():
            with self._locks[service.id]:
                instance = self.instances[service.id]
                deadline = parse_timestamp(instance.idle_deadline)
                if deadline and now >= deadline and not instance.active_holds() and instance.state == LifecycleState.RUNNING:
                    self._stop_locked(service, instance, "idle_timeout")
                next_restart = parse_timestamp(instance.next_restart_at)
                if instance.state == LifecycleState.FAILED and next_restart and now >= next_restart:
                    self._ensure_running_locked(service, instance, "recovery")
                    if instance.state == LifecycleState.RUNNING:
                        instance.holds.pop("recovery", None); self._persist(instance)
                for job in service.document.get("maintenance", {}).get("jobs", []):
                    key = (service.id, job["name"])
                    if key not in self._jobs_running and is_due(job["schedule"], now, instance.schedule_last_run.get(job["name"])):
                        instance.schedule_last_run[job["name"]] = now.isoformat(); self._persist(instance)
                        due.append(key)
        for service_id, job_id in due:
            self.run_maintenance(service_id, job_id)
        return self.list_status()

    def reconcile(self):
        for service in self.registry.services.values():
            with self._locks[service.id]:
                self._reconcile_locked(service, self.instances[service.id])
        return self.list_status()

    def _reconcile_locked(self, service, instance):
        lifecycle = service.document["lifecycle"]
        if lifecycle["mode"] == "always_on":
            instance.holds["always_on"] = 1
        else:
            instance.holds.pop("always_on", None)
        if instance.admin_intent:
            instance.holds["admin"] = 1
        alive = bool(self._driver(service).status(instance, self._declaration(service)).get("alive"))
        if instance.state in STALE_STATES:
            if instance.state == LifecycleState.STOPPING:
                self._transition(instance, LifecycleState.FAILED if alive else LifecycleState.STOPPED, "reconcile_stale")
            elif alive:
                if instance.state == LifecycleState.STARTING:
                    self._transition(instance, LifecycleState.READY, "reconcile_adopt")
                self._transition(instance, LifecycleState.RUNNING, "reconcile_adopt")
            else:
                self._mark_failed_locked(service, instance, DriverError("stale transient state with no live runtime"), "reconcile_stale")
                self._transition(instance, LifecycleState.STOPPED, "reconcile_reset")
        elif instance.state in (LifecycleState.RUNNING, LifecycleState.MAINTENANCE) and not alive:
            self._mark_failed_locked(service, instance, DriverError("runtime is not alive"), "reconcile_failure")
            if instance.active_holds():
                self._restart_after_failure_locked(service, instance)
            else:
                self._transition(instance, LifecycleState.STOPPED, "reconcile_no_holds")
        elif instance.state == LifecycleState.MAINTENANCE and alive:
            self._transition(instance, LifecycleState.RUNNING, "reconcile_abandoned_maintenance")
        elif instance.state == LifecycleState.STOPPED and alive:
            self._transition(instance, LifecycleState.STARTING, "reconcile_adopt")
            self._transition(instance, LifecycleState.READY, "reconcile_adopt")
            self._transition(instance, LifecycleState.RUNNING, "reconcile_adopt")
        if instance.state == LifecycleState.FAILED and alive:
            self._transition(instance, LifecycleState.STARTING, "reconcile_adopt")
            self._transition(instance, LifecycleState.READY, "reconcile_adopt")
            self._transition(instance, LifecycleState.RUNNING, "reconcile_adopt")
        if instance.active_holds() and instance.state == LifecycleState.STOPPED:
            self._ensure_running_locked(service, instance, "reconcile")
        elif instance.active_holds() and instance.state == LifecycleState.FAILED and not instance.restart_exhausted:
            eligible = parse_timestamp(instance.next_restart_at)
            if eligible is None or self.clock.now() >= eligible:
                self._ensure_running_locked(service, instance, "reconcile")
        self._schedule_idle_locked(service, instance)
        self._persist(instance)

    def status(self, service_id):
        service = self._service(service_id)
        with self._locks[service.id]:
            return self.instances[service.id].to_dict()

    def list_status(self):
        return [self.status(service_id) for service_id in sorted(self.instances)]

    def _validate_jobs(self):
        for service in self.registry.services.values():
            names = set()
            for job in service.document.get("maintenance", {}).get("jobs", []):
                if job["name"] in names:
                    raise SupervisorError(f"duplicate maintenance job {service.id}/{job['name']}")
                names.add(job["name"])
                is_due(job["schedule"], self.clock.now(), self.clock.now().isoformat())
