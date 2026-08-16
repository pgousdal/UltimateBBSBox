import datetime as dt
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ubb_registry import load_registry  # noqa: E402
from ubb_supervisor import (FakeClock, FakeDriver, InvalidTransitionError,
                            LifecycleState, ReadinessTimeoutError,
                            RestartLimitExceededError, ServiceBusyError,
                            Supervisor)  # noqa: E402


class Fixture:
    def __init__(self, root, *, mode="on_demand", sharing="multiuser", idle=10,
                 restart="on_failure", max_restarts=3, readiness=None, maintenance=True):
        self.root = pathlib.Path(root)
        for directory in ("services", "endpoints", "integrations"):
            (self.root / directory).mkdir(parents=True)
        endpoint = {"kind": "endpoint", "schema_version": 1, "id": "fake-endpoint",
                    "type": "local_process", "command": ["/bin/false"]}
        lifecycle = {"mode": mode, "sharing": sharing, "idle_timeout_seconds": idle,
                     "startup_timeout_seconds": 2, "restart": restart,
                     "max_restarts": max_restarts, "restart_window_seconds": 60,
                     "restart_backoff_seconds": 0,
                     "readiness": readiness or {"type": "driver_specific"},
                     "shutdown_policy": "when_idle"}
        service = {"kind": "service", "schema_version": 1, "id": "test-service",
                   "service": {"type": "bbs", "title": "Test service"},
                   "endpoint": "fake-endpoint", "exposure": {"main_menu": False, "via_bbs": []},
                   "lifecycle": lifecycle}
        if maintenance:
            service["maintenance"] = {"jobs": [
                {"name": "exchange", "schedule": "every 6h", "action": "network_exchange",
                 "wake_if_stopped": True, "shutdown_after": True, "timeout_seconds": 30},
                {"name": "nightly", "schedule": "daily at 03:00", "action": "nightly",
                 "wake_if_stopped": True, "shutdown_after": True},
            ]}
        (self.root / "endpoints/fake.yml").write_text(yaml.safe_dump(endpoint), encoding="utf-8")
        (self.root / "services/test.yml").write_text(yaml.safe_dump(service), encoding="utf-8")


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, **fixture_args):
        catalog = self.base / "catalog"
        Fixture(catalog, **fixture_args)
        registry = load_registry(catalog)
        clock = FakeClock(dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.timezone.utc))
        driver = FakeDriver()
        supervisor = Supervisor(registry, self.base / "state", lambda _service: driver, clock)
        return supervisor, driver, clock, registry

    def test_start_transitions_to_running_and_journals_all_states(self):
        supervisor, driver, _, _ = self.make(restart="never")
        value = supervisor.start("test-service")
        self.assertEqual(value["state"], "running")
        self.assertEqual(driver.start_calls, 1)
        events = [json.loads(line) for line in (self.base / "state/events.jsonl").read_text().splitlines()]
        self.assertEqual([item["new_state"] for item in events], ["starting", "ready", "running"])
        self.assertTrue(all(item["instance_id"] == "test-service:shared" for item in events))

    def test_invalid_transition_rejected(self):
        supervisor, _, _, _ = self.make()
        with self.assertRaises(InvalidTransitionError):
            supervisor.transition("test-service", LifecycleState.RUNNING)

    def test_on_demand_start_and_always_on_reconcile(self):
        supervisor, driver, _, _ = self.make(mode="always_on")
        supervisor.reconcile()
        self.assertEqual(supervisor.status("test-service")["state"], "running")
        self.assertEqual(supervisor.status("test-service")["holds"], {"always_on": 1})
        self.assertEqual(driver.start_calls, 1)

    def test_always_on_failure_restarts(self):
        supervisor, driver, _, _ = self.make(mode="always_on")
        supervisor.reconcile(); driver.alive.clear(); supervisor.reconcile()
        self.assertEqual(supervisor.status("test-service")["state"], "running")
        self.assertEqual(driver.start_calls, 2)

    def test_restart_limit_exhaustion(self):
        supervisor, driver, _, _ = self.make(mode="always_on", max_restarts=2)
        supervisor.reconcile()
        for _ in range(2):
            driver.alive.clear(); supervisor.notify_failure("test-service")
        driver.alive.clear()
        with self.assertRaises(RestartLimitExceededError):
            supervisor.notify_failure("test-service")
        self.assertEqual(supervisor.status("test-service")["state"], "failed")
        self.assertTrue(supervisor.status("test-service")["restart_exhausted"])
        supervisor.reconcile()
        self.assertEqual(driver.start_calls, 3)

    def test_restart_backoff_is_respected(self):
        supervisor, driver, clock, _ = self.make(mode="always_on", maintenance=False)
        service = supervisor.registry.service("test-service")
        service.document["lifecycle"]["restart_backoff_seconds"] = 10
        supervisor.reconcile(); driver.alive.clear(); supervisor.notify_failure("test-service")
        self.assertEqual(supervisor.status("test-service")["state"], "failed")
        supervisor.tick(); self.assertEqual(driver.start_calls, 1)
        clock.advance(10); supervisor.tick()
        self.assertEqual(driver.start_calls, 2)

    def test_readiness_timeout(self):
        supervisor, driver, _, _ = self.make(restart="never")
        driver.ready_after_checks = 1000
        with self.assertRaises(ReadinessTimeoutError): supervisor.start("test-service")
        self.assertEqual(supervisor.status("test-service")["state"], "failed")

    def test_final_release_idle_shutdown_and_new_session_cancels(self):
        supervisor, driver, clock, _ = self.make(idle=10, restart="never")
        first = supervisor.acquire_session("test-service"); supervisor.release_session("test-service", first)
        self.assertIsNotNone(supervisor.status("test-service")["idle_deadline"])
        clock.advance(5); second = supervisor.acquire_session("test-service")
        self.assertIsNone(supervisor.status("test-service")["idle_deadline"])
        clock.advance(10); supervisor.tick()
        self.assertEqual(supervisor.status("test-service")["state"], "running")
        supervisor.release_session("test-service", second); clock.advance(10); supervisor.tick()
        self.assertEqual(supervisor.status("test-service")["state"], "stopped")
        self.assertEqual(driver.stop_calls, 1)

    def test_single_session_rejects_second(self):
        supervisor, _, _, _ = self.make(sharing="single_session", restart="never")
        supervisor.acquire_session("test-service")
        with self.assertRaises(ServiceBusyError): supervisor.acquire_session("test-service")

    def test_multiuser_holds_until_final_release(self):
        supervisor, _, clock, _ = self.make(idle=0, restart="never")
        first = supervisor.acquire_session("test-service"); second = supervisor.acquire_session("test-service")
        self.assertEqual(supervisor.status("test-service")["active_session_count"], 2)
        supervisor.release_session("test-service", first); supervisor.tick()
        self.assertEqual(supervisor.status("test-service")["state"], "running")
        supervisor.release_session("test-service", second); supervisor.tick()
        self.assertEqual(supervisor.status("test-service")["state"], "stopped")

    def test_scheduled_maintenance_wakes_and_stops_on_demand(self):
        supervisor, driver, _, _ = self.make(restart="never")
        supervisor.tick()
        self.assertIn("exchange", driver.maintenance_calls)
        self.assertEqual(supervisor.status("test-service")["state"], "stopped")

    def test_maintenance_on_running_service_does_not_stop(self):
        supervisor, driver, _, _ = self.make(restart="never")
        supervisor.start("test-service"); supervisor.run_maintenance("test-service", "exchange")
        self.assertEqual(supervisor.status("test-service")["state"], "running")
        self.assertEqual(driver.stop_calls, 0)

    def test_caller_arriving_during_maintenance_keeps_service_running(self):
        supervisor, driver, _, _ = self.make(restart="never")
        driver.maintenance_entered = threading.Event(); driver.maintenance_continue = threading.Event()
        thread = threading.Thread(target=supervisor.run_maintenance, args=("test-service", "exchange"))
        thread.start(); self.assertTrue(driver.maintenance_entered.wait(2))
        session = supervisor.acquire_session("test-service")
        driver.maintenance_continue.set(); thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(supervisor.status("test-service")["state"], "running")
        self.assertEqual(supervisor.status("test-service")["holds"], {"sessions": 1})
        supervisor.release_session("test-service", session)

    def test_duplicate_start_calls_coalesce(self):
        supervisor, driver, _, _ = self.make(restart="never")
        threads = [threading.Thread(target=supervisor.start, args=("test-service",)) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(driver.start_calls, 1)

    def test_stop_start_race_serializes(self):
        supervisor, driver, _, _ = self.make(restart="never")
        supervisor.start("test-service")
        driver.stop_entered = threading.Event(); driver.stop_continue = threading.Event()
        stop = threading.Thread(target=supervisor.stop, args=("test-service", True))
        start = threading.Thread(target=supervisor.start, args=("test-service",))
        stop.start(); self.assertTrue(driver.stop_entered.wait(2)); start.start()
        driver.stop_continue.set(); stop.join(2); start.join(2)
        self.assertEqual(supervisor.status("test-service")["state"], "running")
        self.assertEqual(driver.start_calls, 2)

    def test_scheduler_does_not_run_job_twice(self):
        supervisor, driver, _, _ = self.make(restart="never")
        supervisor.tick(); first_count = driver.maintenance_calls.count("exchange")
        supervisor.tick()
        self.assertEqual(driver.maintenance_calls.count("exchange"), first_count)

    def test_daily_local_time_schedule(self):
        supervisor, driver, clock, _ = self.make(restart="never")
        supervisor.tick()
        self.assertNotIn("nightly", driver.maintenance_calls)
        clock.advance(3 * 3600); supervisor.tick(); supervisor.tick()
        self.assertEqual(driver.maintenance_calls.count("nightly"), 1)

    def test_persistent_state_round_trip(self):
        supervisor, driver, clock, registry = self.make(restart="never")
        supervisor.start("test-service")
        restored = Supervisor(registry, self.base / "state", lambda _service: driver, clock)
        self.assertEqual(restored.status("test-service")["state"], "running")
        self.assertTrue(restored.status("test-service")["admin_intent"])

    def test_stale_starting_recovery(self):
        supervisor, driver, clock, registry = self.make(restart="never")
        supervisor.transition("test-service", "starting")
        restored = Supervisor(registry, self.base / "state", lambda _service: driver, clock)
        restored.reconcile()
        self.assertEqual(restored.status("test-service")["state"], "stopped")

    def test_always_on_recovers_after_supervisor_restart(self):
        supervisor, driver, clock, registry = self.make(mode="always_on")
        restored = Supervisor(registry, self.base / "state", lambda _service: driver, clock)
        restored.reconcile()
        self.assertEqual(restored.status("test-service")["state"], "running")

    def test_cli_json_status(self):
        supervisor, _, _, registry = self.make(restart="never")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/ubb-supervisor.py"), "--catalog", str(self.base / "catalog"),
             "--state-dir", str(self.base / "state"), "--json", "status", "test-service"],
            cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], supervisor.status("test-service")["state"])


if __name__ == "__main__":
    unittest.main()
