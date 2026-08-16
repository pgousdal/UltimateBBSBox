import datetime as dt
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ubb_registry import load_registry  # noqa: E402
from ubb_router import RouteRequest, Router  # noqa: E402
from ubb_runtime import (FSUAEAdapter, ProcessAdapter, QEMUAdapter,
                         RuntimeAdapterRegistry, RuntimeConfigError,
                         RuntimeManager, RuntimeStreamError,
                         RuntimeStreamResolver, SIMHAdapter,
                         UnsupportedRuntimeError, VICEAdapter,
                         check_readiness)  # noqa: E402
from ubb_supervisor import FakeClock, InstanceState, Supervisor  # noqa: E402


PYTHON = str(pathlib.Path(sys.executable).resolve())


def instance(name="runtime-test"):
    return InstanceState(name, f"{name}:shared")


def python_config(code, *args, **extra):
    return {"executable": PYTHON, "argv": ["-u", "-c", code, *args],
            "working_directory": str(pathlib.Path.cwd()), **extra}


class AdapterTests(unittest.TestCase):
    def setUp(self): self.temp = tempfile.TemporaryDirectory(); self.base = pathlib.Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_runtime_registry_and_unknown_runtime(self):
        registry = RuntimeAdapterRegistry.defaults()
        self.assertEqual(registry.get("native").runtime_name, "native")
        self.assertEqual(registry.names(), tuple(sorted(registry.names())))
        with self.assertRaises(Exception): registry.get("unknown-runtime")
        for name in ("dos", "mame", "hatari"):
            with self.assertRaises(UnsupportedRuntimeError): registry.get(name).prepare(instance(), {})

    def test_local_process_start_status_duplicate_and_graceful_stop(self):
        adapter = ProcessAdapter(); state = instance()
        config = python_config("import time; time.sleep(60)", stop_timeout_seconds=1)
        first = adapter.start(state, config); second = adapter.start(state, config)
        self.assertTrue(first.started); self.assertTrue(second.already_running)
        self.assertEqual(first.pid, second.pid); self.assertTrue(adapter.status(state, config).alive)
        stopped = adapter.stop(state, config)
        self.assertTrue(stopped.stopped); self.assertFalse(adapter.status(state, config).alive)

    def test_forced_stop_fallback(self):
        adapter = ProcessAdapter(); state = instance()
        ready = self.base / "ready"
        code = "import pathlib,signal,time,sys; signal.signal(signal.SIGTERM,lambda *x:None); pathlib.Path(sys.argv[1]).write_text('ok'); time.sleep(60)"
        config = python_config(code, str(ready), stop_timeout_seconds=0.05)
        adapter.start(state, config)
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline: time.sleep(0.01)
        self.assertTrue(ready.exists())
        self.assertTrue(adapter.stop(state, config).forced)

    def test_argv_and_environment_preserved_without_inheriting_secrets(self):
        adapter = ProcessAdapter(); state = instance()
        output = self.base / "output.json"
        code = "import json,os,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(json.dumps({'argv':sys.argv[2:],'value':os.getenv('SAFE_VALUE'),'home':os.getenv('HOME')}))"
        config = python_config(code, str(output), "space value", "--literal=$HOME",
                               environment={"SAFE_VALUE": "configured"}, stop_timeout_seconds=1)
        adapter.start(state, config)
        deadline = time.monotonic() + 2
        while adapter.status(state, config).alive and time.monotonic() < deadline: time.sleep(0.01)
        value = json.loads(output.read_text())
        self.assertEqual(value["argv"], ["space value", "--literal=$HOME"])
        self.assertEqual(value["value"], "configured"); self.assertIsNone(value["home"])
        adapter.cleanup(state, config)

    def test_environment_rejects_loader_injection(self):
        with self.assertRaises(RuntimeConfigError):
            ProcessAdapter().validate_config(python_config("pass", environment={"LD_PRELOAD": "/tmp/x"}))

    def test_pty_roundtrip_eof_resize_and_idempotent_close(self):
        adapter = ProcessAdapter(); state = instance()
        config = python_config("import os; data=os.read(0,1); os.write(1,data)", pty=True, stream={"type": "pty"})
        adapter.start(state, config); stream = adapter.open_stream(state, config)
        stream.resize(100, 30); self.assertEqual(stream.write(b"Z"), 1); self.assertEqual(stream.read(1), b"Z")
        deadline = time.monotonic() + 2
        while adapter.status(state, config).alive and time.monotonic() < deadline: time.sleep(0.01)
        self.assertEqual(stream.read(1), b""); stream.close(); stream.close(); adapter.cleanup(state, config)

    def test_stdio_stream_roundtrip(self):
        adapter = ProcessAdapter(); state = instance()
        config = python_config("import os; os.write(1,os.read(0,1))", stream={"type": "stdio"})
        adapter.start(state, config); stream = adapter.open_stream(state, config)
        stream.write(b"S"); self.assertEqual(stream.read(1), b"S"); stream.close(); adapter.stop(state, config)

    def test_readiness_immediate_process_file_and_command(self):
        state = instance(); adapter = ProcessAdapter(); config = python_config("import time; time.sleep(60)")
        adapter.start(state, config)
        self.assertTrue(adapter.readiness(state, config, {"type": "immediate"}).ready)
        self.assertTrue(adapter.readiness(state, config, {"type": "process_alive"}).ready)
        marker = self.base / "marker"; marker.write_text("ready")
        self.assertTrue(check_readiness({"type": "file_exists", "path": str(marker)}, lambda: adapter.status(state, config)).ready)
        self.assertTrue(check_readiness({"type": "command_exit_zero", "command": [PYTHON, "-c", "pass"]}, lambda: adapter.status(state, config)).ready)
        self.assertFalse(check_readiness({"type": "command_exit_zero", "command": [PYTHON, "-c", "raise SystemExit(3)"]}, lambda: adapter.status(state, config)).ready)
        adapter.stop(state, config)

    def test_tcp_readiness_success_and_failure(self):
        server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1); port = server.getsockname()[1]
        self.assertTrue(check_readiness({"type": "tcp_port", "host": "127.0.0.1", "port": port, "timeout_seconds": .2}, lambda: None).ready)
        server.close()
        self.assertFalse(check_readiness({"type": "tcp_port", "host": "127.0.0.1", "port": port, "timeout_seconds": .05}, lambda: None).ready)

    def test_emulator_adapters_build_only_generic_commands(self):
        config_file = self.base / "machine.conf"; config_file.write_text("fixture")
        fake = self.base / "fake-emulator"
        fake.write_text("#!/usr/bin/python3\nimport time\ntime.sleep(60)\n"); fake.chmod(0o755)
        base = {"executable": str(fake), "argv": ["--flag"], "working_directory": str(self.base), "stop_timeout_seconds": .2}
        cases = [(FSUAEAdapter(), {**base, "config_file": str(config_file)}, [str(fake), str(config_file), "--flag"]),
                 (VICEAdapter(), base, [str(fake), "--flag"]),
                 (QEMUAdapter(), base, [str(fake), "--flag"]),
                 (SIMHAdapter(), {**base, "config_file": str(config_file)}, [str(fake), "--flag", str(config_file)])]
        for number, (adapter, config, expected) in enumerate(cases):
            self.assertEqual(adapter.build_command(config), expected)
            state = instance(f"emulator-{number}"); adapter.start(state, config)
            self.assertTrue(adapter.status(state, config).alive); self.assertTrue(adapter.stop(state, config).stopped)

    def test_stale_pid_reconciliation_is_conservative(self):
        state = instance(); state.runtime = {"pid": os.getpid(), "process_executable": "/definitely/not-this",
                                             "process_start_ticks": "wrong"}
        status = ProcessAdapter().status(state, python_config("pass"))
        self.assertFalse(status.alive); self.assertFalse(status.identity_verified)

    def test_no_shell_true_in_runtime_core(self):
        source = "\n".join(path.read_text() for path in (ROOT / "scripts/ubb_runtime").glob("*.py"))
        self.assertNotIn("shell=True", source)
        for product in ("mystic-main", "abbs", "nikom", "c-net"):
            self.assertNotIn(product, source.lower())


class RuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.base = pathlib.Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def catalog(self, config, *, readiness=None, runtime="native"):
        root = self.base / "catalog"
        for directory in ("services", "endpoints", "integrations"): (root / directory).mkdir(parents=True, exist_ok=True)
        ep = {"kind": "endpoint", "schema_version": 1, "id": "runtime-endpoint", "type": "local_process", "command": [PYTHON, "-c", "pass"]}
        svc = {"kind": "service", "schema_version": 1, "id": "runtime-service",
               "service": {"type": "other", "title": "Synthetic runtime"}, "endpoint": "runtime-endpoint",
               "integration": "runtime-integration", "exposure": {"main_menu": True, "via_bbs": []},
               "lifecycle": {"mode": "on_demand", "sharing": "multiuser", "idle_timeout_seconds": 0,
                             "startup_timeout_seconds": 1, "restart": "never", "shutdown_policy": "when_idle",
                             "readiness": readiness or {"type": "driver_specific"}}}
        integration = {"kind": "integration", "schema_version": 1, "id": "runtime-integration",
                       "target": "runtime-service", "automation_level": "fully_automated", "runtime": runtime,
                       "runtime_config": config, "installation": {"steps": [{"type": "automated", "action": "synthetic"}]},
                       "qualification": {"checks": []}}
        for directory, document in (("endpoints", ep), ("services", svc), ("integrations", integration)):
            (root / directory / "fixture.yml").write_text(yaml.safe_dump(document), encoding="utf-8")
        return load_registry(root)

    def test_m3_uses_adapter_and_persists_runtime_state(self):
        config = python_config("import time; time.sleep(60)", readiness={"type": "process_alive"})
        registry = self.catalog(config); clock = FakeClock()
        supervisor = Supervisor(registry, self.base / "state", clock=clock)
        supervisor.start("runtime-service")
        state = supervisor.status("runtime-service")
        self.assertEqual(state["runtime"]["adapter"], "native"); self.assertIsInstance(state["runtime"]["pid"], int)
        persisted = json.loads((self.base / "state/instances/runtime-service.json").read_text())
        self.assertEqual(persisted["runtime"]["adapter"], "native")
        supervisor.stop("runtime-service", force=True)

    def test_runtime_start_and_readiness_failures_reach_m3(self):
        bad = {"executable": "/does/not/exist", "argv": []}
        supervisor = Supervisor(self.catalog(bad), self.base / "bad-state", clock=FakeClock())
        with self.assertRaises(RuntimeConfigError): supervisor.start("runtime-service")
        self.assertEqual(supervisor.status("runtime-service")["state"], "failed")

        missing = self.base / "never-created"
        config = python_config("import time; time.sleep(60)", readiness={"type": "file_exists", "path": str(missing)}, stop_timeout_seconds=.2)
        supervisor = Supervisor(self.catalog(config), self.base / "ready-state", clock=FakeClock())
        with self.assertRaises(Exception): supervisor.start("runtime-service")
        self.assertEqual(supervisor.status("runtime-service")["state"], "failed")

    def test_m4_opens_runtime_pty_stream_and_releases_failed_stream_hold(self):
        config = python_config("import os; os.write(1,os.read(0,1))", pty=True, stream={"type": "pty"}, readiness={"type": "process_alive"})
        registry = self.catalog(config); manager = RuntimeManager(registry, self.base / "state/runtime")
        supervisor = Supervisor(registry, self.base / "state", clock=FakeClock(), runtime_manager=manager)
        router = Router(registry, supervisor, self.base / "router",
                        runtime_stream_resolver=RuntimeStreamResolver(manager, supervisor))
        handle = router.open_session(RouteRequest("runtime-service")); handle.write(b"R"); self.assertEqual(handle.read(1), b"R")
        handle.close(); self.assertEqual(supervisor.status("runtime-service")["active_session_count"], 0)
        supervisor.tick()

        no_stream = python_config("import time; time.sleep(60)", readiness={"type": "process_alive"})
        registry = self.catalog(no_stream); manager = RuntimeManager(registry, self.base / "state2/runtime")
        supervisor = Supervisor(registry, self.base / "state2", clock=FakeClock(), runtime_manager=manager)
        router = Router(registry, supervisor, self.base / "router2", runtime_stream_resolver=RuntimeStreamResolver(manager, supervisor))
        with self.assertRaises(RuntimeStreamError): router.open_session(RouteRequest("runtime-service"))
        self.assertEqual(supervisor.status("runtime-service")["active_session_count"], 0)
        supervisor.stop("runtime-service", force=True)

    def test_m4_opens_runtime_configured_tcp_stream(self):
        server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(1); port = server.getsockname()[1]
        received = []
        def serve():
            connection, _ = server.accept()
            with connection:
                received.append(connection.recv(8)); connection.sendall(b"reply")
            server.close()
        thread = threading.Thread(target=serve); thread.start()
        config = python_config("import time; time.sleep(60)", readiness={"type": "process_alive"},
                               stream={"type": "tcp", "host": "127.0.0.1", "port": port,
                                       "connect_timeout_seconds": .5})
        registry = self.catalog(config); manager = RuntimeManager(registry, self.base / "tcp-state/runtime")
        supervisor = Supervisor(registry, self.base / "tcp-state", clock=FakeClock(), runtime_manager=manager)
        router = Router(registry, supervisor, self.base / "tcp-router",
                        runtime_stream_resolver=RuntimeStreamResolver(manager, supervisor))
        handle = router.open_session(RouteRequest("runtime-service")); handle.write(b"request")
        self.assertEqual(handle.read(), b"reply"); handle.close(); supervisor.stop("runtime-service", force=True)
        thread.join(2); self.assertEqual(received, [b"request"])


if __name__ == "__main__": unittest.main()
