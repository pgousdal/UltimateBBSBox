import datetime as dt
import json
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ubb_registry import load_registry  # noqa: E402
from ubb_router import (AuthorizationError, HandoffMode,
                        InvalidSessionTransitionError, MemoryConnector,
                        MemoryStream, RouteRequest, RouteType, Router,
                        SessionBusyError, SessionState,
                        TCPConnector, TerminalCapabilities, TransportError,
                        UnknownServiceError, UnsupportedTransportError)  # noqa: E402
from ubb_supervisor import FakeClock, FakeDriver, ServiceBusyError, Supervisor  # noqa: E402


def endpoint(endpoint_id, endpoint_type="tcp", **values):
    result = {"kind": "endpoint", "schema_version": 1, "id": endpoint_id, "type": endpoint_type}
    if endpoint_type == "tcp": result.update(host="127.0.0.1", port=2323, protocol="raw_tcp", connect_timeout_seconds=1)
    elif endpoint_type == "ssh": result.update(host="shell.internal", protocol="ssh")
    elif endpoint_type == "remote_supervisor": result.update(host="remote.internal", remote_service_id="target")
    result.update(values)
    return result


def service(service_id, endpoint_id, *, service_type="bbs", main=True, via=(), sharing="multiuser", direct=True):
    return {"kind": "service", "schema_version": 1, "id": service_id,
            "service": {"type": service_type, "title": service_id}, "endpoint": endpoint_id,
            "exposure": {"main_menu": main, "via_bbs": list(via)},
            "access": {"direct_allowed": direct},
            "lifecycle": {"mode": "on_demand", "sharing": sharing, "idle_timeout_seconds": 0,
                          "startup_timeout_seconds": 2, "restart": "never",
                          "readiness": {"type": "driver_specific"}, "shutdown_policy": "when_idle"}}


class CatalogFixture:
    def __init__(self, root):
        self.root = pathlib.Path(root)
        for directory in ("services", "endpoints", "integrations"):
            (self.root / directory).mkdir(parents=True)
        documents = [
            endpoint("direct-ep"), endpoint("via-ep"), endpoint("hidden-ep"),
            endpoint("single-ep"), endpoint("ssh-ep", "ssh"), endpoint("remote-ep", "remote_supervisor"),
            service("alpha-bbs", "direct-ep"), service("zeta-bbs", "direct-ep"),
            service("via-shell", "via-ep", service_type="shell", main=False, via=("alpha-bbs",), direct=False),
            service("hidden-service", "hidden-ep", service_type="other", main=False, direct=False),
            service("single-service", "single-ep", service_type="door", sharing="single_session"),
            service("ssh-service", "ssh-ep", service_type="shell"),
            service("remote-service", "remote-ep", service_type="shell"),
        ]
        for document in documents:
            directory = "endpoints" if document["kind"] == "endpoint" else "services"
            (self.root / directory / f"{document['id']}.yml").write_text(yaml.safe_dump(document), encoding="utf-8")


class FreshMemoryConnector:
    def __init__(self):
        self.streams = []
        self.timeouts = []
        self.observe = None

    def connect(self, endpoint, timeout):
        self.timeouts.append(timeout)
        if self.observe: self.observe()
        stream = MemoryStream([b"hello"]); self.streams.append(stream); return stream


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = pathlib.Path(self.temp.name)
        CatalogFixture(self.base / "catalog")
        self.registry = load_registry(self.base / "catalog")
        self.clock = FakeClock(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
        self.driver = FakeDriver()
        self.supervisor = Supervisor(self.registry, self.base / "supervisor", lambda _service: self.driver, self.clock)
        self.connector = FreshMemoryConnector()
        counter = iter(f"session-{number}" for number in range(100))
        self.router = Router(self.registry, self.supervisor, self.base / "router",
                             {"tcp": self.connector}, self.clock, id_factory=lambda: next(counter))

    def tearDown(self): self.temp.cleanup()

    def direct(self, target="alpha-bbs", terminal=None, metadata=None):
        return RouteRequest(target, RouteType.DIRECT, terminal=terminal or TerminalCapabilities(), caller_metadata=metadata or {})

    def test_direct_authorized_and_lifecycle_hold_precedes_active(self):
        def observe():
            status = self.supervisor.status("alpha-bbs")
            self.assertEqual(status["active_session_count"], 1)
            self.assertEqual(status["state"], "running")
        self.connector.observe = observe
        handle = self.router.open_session(self.direct())
        self.assertEqual(handle.session["state"], "active")
        self.assertIsNotNone(handle.session["lifecycle_session_id"])

    def test_direct_hidden_and_via_only_are_denied(self):
        for target in ("hidden-service", "via-shell"):
            with self.assertRaises(AuthorizationError): self.router.open_session(self.direct(target))
            self.assertEqual(self.supervisor.status(target)["active_session_count"], 0)

    def test_via_allowed_and_wrong_bbs_denied(self):
        alpha = self.router.open_session(self.direct("alpha-bbs"))
        zeta = self.router.open_session(self.direct("zeta-bbs"))
        allowed = RouteRequest("via-shell", RouteType.VIA_SERVICE, "alpha-bbs")
        self.assertEqual(self.router.open_session(allowed, parent_session_id=alpha.id).session["state"], "active")
        with self.assertRaises(AuthorizationError):
            self.router.open_session(RouteRequest("via-shell", RouteType.VIA_SERVICE, "zeta-bbs"), parent_session_id=zeta.id)

    def test_via_origin_service_id_cannot_be_forged(self):
        request = RouteRequest("via-shell", RouteType.VIA_SERVICE, "alpha-bbs")
        with self.assertRaises(SessionBusyError): self.router.open_session(request)
        wrong_parent = self.router.open_session(self.direct("zeta-bbs"))
        with self.assertRaises(SessionBusyError): self.router.open_session(request, parent_session_id=wrong_parent.id)

    def test_unknown_target(self):
        with self.assertRaises(UnknownServiceError): self.router.open_session(self.direct("missing"))

    def test_close_releases_hold_exactly_once(self):
        handle = self.router.open_session(self.direct())
        threads = [threading.Thread(target=handle.close) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        handle.close()
        self.assertEqual(self.supervisor.status("alpha-bbs")["active_session_count"], 0)
        self.assertEqual(handle.session["state"], "closed")

    def test_connect_failure_releases_hold_and_records_failed(self):
        self.router.connectors["tcp"] = MemoryConnector(error=RuntimeError("secret-password"))
        with self.assertRaises(RuntimeError): self.router.open_session(self.direct(metadata={"password": "never-log-me"}))
        self.assertEqual(self.supervisor.status("alpha-bbs")["active_session_count"], 0)
        self.assertEqual(self.router.list_sessions()[0]["state"], "failed")
        journal = (self.base / "router/events.jsonl").read_text()
        self.assertNotIn("secret-password", journal); self.assertNotIn("never-log-me", journal)

    def test_single_and_multiuser_semantics_come_from_m3(self):
        first = self.router.open_session(self.direct("single-service"))
        with self.assertRaises(ServiceBusyError): self.router.open_session(self.direct("single-service"))
        first.close()
        one = self.router.open_session(self.direct()); two = self.router.open_session(self.direct())
        self.assertEqual(self.supervisor.status("alpha-bbs")["active_session_count"], 2)
        one.close(); self.assertEqual(self.supervisor.status("alpha-bbs")["active_session_count"], 1)
        two.close()

    def test_terminal_metadata_roundtrips_extensibly(self):
        terminals = [TerminalCapabilities("cp437", "ansi", 80, 25, 2400, False, "crlf"),
                     TerminalCapabilities("petscii", "commodore", 40, 25, extensions={"color": True}),
                     TerminalCapabilities("atascii", "obscure-custom", 40, 24)]
        for terminal in terminals:
            handle = self.router.open_session(self.direct(terminal=terminal))
            self.assertEqual(handle.session["terminal"], terminal.to_dict()); handle.close()

    def test_raw_stream_read_write_and_eof_cleanup(self):
        handle = self.router.open_session(self.direct())
        self.assertEqual(handle.read(), b"hello")
        self.assertEqual(handle.write(b"raw bytes\x00"), 10)
        self.assertEqual(handle.read(), b"")
        self.assertEqual(handle.session["termination_reason"], "endpoint_eof")
        self.assertEqual(self.supervisor.status("alpha-bbs")["active_session_count"], 0)

    def test_journal_has_metadata_not_terminal_content_or_credentials(self):
        handle = self.router.open_session(self.direct(metadata={"password": "top-secret"}))
        handle.write(b"private message top-secret"); handle.close("untrusted top-secret reason")
        journal = (self.base / "router/events.jsonl").read_text()
        self.assertIn('"event_type":"connected"', journal)
        self.assertNotIn("private message", journal); self.assertNotIn("top-secret", journal)

    def test_handoff_return_to_origin_and_authorization(self):
        parent = self.router.open_session(self.direct())
        child = self.router.handoff(parent.id, "via-shell", return_to_origin=True)
        self.assertEqual(parent.session["state"], "handing_off")
        self.assertEqual(child.session["parent_session_id"], parent.id)
        self.assertEqual(child.session["handoff_mode"], "return_to_origin")
        child.close(); self.assertEqual(parent.session["state"], "active")
        with self.assertRaises(AuthorizationError): self.router.handoff(parent.id, "hidden-service")

    def test_parent_close_during_handoff_and_duplicate_handoff(self):
        parent = self.router.open_session(self.direct())
        child = self.router.handoff(parent.id, "via-shell")
        with self.assertRaises(SessionBusyError): self.router.handoff(parent.id, "via-shell")
        parent.close("parent_closed"); child.close()
        self.assertEqual(parent.session["state"], "closed")

    def test_replace_handoff_closes_parent(self):
        parent = self.router.open_session(self.direct())
        child = self.router.handoff(parent.id, "via-shell", return_to_origin=False)
        self.assertEqual(parent.session["state"], "closed")
        self.assertEqual(child.session["handoff_mode"], "replace")

    def test_unsupported_ssh_and_remote_supervisor_fail_explicitly(self):
        for target in ("ssh-service", "remote-service"):
            with self.assertRaises(UnsupportedTransportError): self.router.open_session(self.direct(target))
            self.assertEqual(self.supervisor.status(target)["active_session_count"], 0)

    def test_direct_listing_deterministic(self):
        self.assertEqual([service.id for service in self.router.list_direct_services()],
                         ["alpha-bbs", "remote-service", "single-service", "ssh-service", "zeta-bbs"])

    def test_invalid_session_transition(self):
        handle = self.router.open_session(self.direct()); session = self.router._session(handle.id)
        with self.assertRaises(InvalidSessionTransitionError):
            self.router._transition(session, SessionState.CREATED, "invalid")

    def test_connect_timeout_passed_to_connector(self):
        self.router.open_session(self.direct())
        self.assertEqual(self.connector.timeouts, [1.0])

    def test_cli_authorization_and_denied_bypass(self):
        cli = str(ROOT / "scripts/ubb-router.py")
        good = subprocess.run([sys.executable, cli, "--catalog", str(self.base / "catalog"), "authorize", "via-shell", "--via", "alpha-bbs"], cwd=ROOT, text=True, capture_output=True)
        bad = subprocess.run([sys.executable, cli, "--catalog", str(self.base / "catalog"), "authorize", "via-shell"], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(good.returncode, 0, good.stderr); self.assertIn("AUTHORIZED", good.stdout)
        self.assertEqual(bad.returncode, 2); self.assertIn("DENIED", bad.stderr)


class TCPRouterTest(unittest.TestCase):
    def test_local_tcp_stream(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary); CatalogFixture(base / "catalog")
            registry = load_registry(base / "catalog")
            server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1)
            port = server.getsockname()[1]
            registry.endpoint("direct-ep").document["port"] = port
            received = []
            def serve():
                connection, _ = server.accept()
                with connection:
                    received.append(connection.recv(16)); connection.sendall(b"pong")
                server.close()
            thread = threading.Thread(target=serve); thread.start()
            clock = FakeClock(); driver = FakeDriver()
            supervisor = Supervisor(registry, base / "supervisor", lambda _service: driver, clock)
            router = Router(registry, supervisor, base / "router", clock=clock)
            handle = router.open_session(RouteRequest("alpha-bbs"))
            handle.write(b"ping"); self.assertEqual(handle.read(), b"pong"); handle.close()
            thread.join(2); self.assertEqual(received, [b"ping"])

    def test_tcp_failure_is_bounded_and_releases_hold(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = pathlib.Path(temporary); CatalogFixture(base / "catalog")
            registry = load_registry(base / "catalog")
            probe = socket.socket(); probe.bind(("127.0.0.1", 0)); port = probe.getsockname()[1]; probe.close()
            registry.endpoint("direct-ep").document["port"] = port
            registry.endpoint("direct-ep").document["connect_timeout_seconds"] = 0.2
            clock = FakeClock(); driver = FakeDriver()
            supervisor = Supervisor(registry, base / "supervisor", lambda _service: driver, clock)
            router = Router(registry, supervisor, base / "router", clock=clock)
            with self.assertRaises(TransportError): router.open_session(RouteRequest("alpha-bbs"))
            self.assertEqual(supervisor.status("alpha-bbs")["active_session_count"], 0)


if __name__ == "__main__": unittest.main()
