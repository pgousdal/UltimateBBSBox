"""Generic runtime-driver contract, fake driver, and local-process driver."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from typing import Protocol

from .errors import DriverError
from .models import InstanceState


class RuntimeDriver(Protocol):
    def start(self, instance: InstanceState, declaration: dict) -> dict: ...
    def stop(self, instance: InstanceState, declaration: dict) -> dict: ...
    def status(self, instance: InstanceState, declaration: dict) -> dict: ...
    def is_ready(self, instance: InstanceState, declaration: dict, readiness: dict) -> bool: ...
    def run_maintenance(self, instance: InstanceState, declaration: dict, job: dict) -> dict: ...


class FakeDriver:
    """Deterministic driver used by tests and embedding applications."""
    def __init__(self):
        self.alive: set[str] = set()
        self.start_calls = 0
        self.stop_calls = 0
        self.maintenance_calls: list[str] = []
        self.start_failures = 0
        self.ready_after_checks = 0
        self.readiness_checks = 0
        self.maintenance_entered: threading.Event | None = None
        self.maintenance_continue: threading.Event | None = None
        self.stop_entered: threading.Event | None = None
        self.stop_continue: threading.Event | None = None

    def start(self, instance, declaration):
        self.start_calls += 1
        if self.start_failures:
            self.start_failures -= 1
            raise DriverError("injected start failure")
        self.alive.add(instance.instance_id)
        return {"started": True}

    def stop(self, instance, declaration):
        self.stop_calls += 1
        if self.stop_entered:
            self.stop_entered.set()
        if self.stop_continue:
            self.stop_continue.wait(timeout=5)
        self.alive.discard(instance.instance_id)
        return {"stopped": True}

    def status(self, instance, declaration):
        return {"alive": instance.instance_id in self.alive}

    def is_ready(self, instance, declaration, readiness):
        self.readiness_checks += 1
        return instance.instance_id in self.alive and self.readiness_checks > self.ready_after_checks

    def run_maintenance(self, instance, declaration, job):
        self.maintenance_calls.append(job["name"])
        if self.maintenance_entered:
            self.maintenance_entered.set()
        if self.maintenance_continue:
            self.maintenance_continue.wait(timeout=5)
        return {"ok": True, "action": job["action"]}


class LocalProcessDriver:
    """Minimal product-neutral driver for local_process endpoint commands."""
    def start(self, instance, declaration):
        command = declaration["endpoint"].get("command")
        if not command:
            raise DriverError("local process endpoint has no command")
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True, close_fds=True)
        instance.runtime["pid"] = process.pid
        return {"started": True, "pid": process.pid}

    def status(self, instance, declaration):
        pid = instance.runtime.get("pid")
        if not isinstance(pid, int) or pid <= 1:
            return {"alive": False}
        try:
            os.kill(pid, 0)
            return {"alive": True, "pid": pid}
        except ProcessLookupError:
            return {"alive": False, "pid": pid}
        except PermissionError:
            return {"alive": True, "pid": pid}

    def stop(self, instance, declaration):
        status = self.status(instance, declaration)
        if status["alive"]:
            try: os.killpg(instance.runtime["pid"], signal.SIGTERM)
            except ProcessLookupError: pass
        instance.runtime.pop("pid", None)
        return {"stopped": True}

    def is_ready(self, instance, declaration, readiness):
        readiness_type = readiness.get("type", "process_alive")
        if readiness_type == "immediate":
            return True
        if readiness_type == "process_alive":
            return bool(self.status(instance, declaration)["alive"])
        if readiness_type == "command_probe":
            command = readiness.get("command")
            if not command:
                raise DriverError("command_probe has no command")
            return subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, timeout=5, check=False).returncode == 0
        raise DriverError("driver_specific readiness requires another runtime driver")

    def run_maintenance(self, instance, declaration, job):
        command = job.get("command")
        if not command:
            raise DriverError("local maintenance requires an explicit command argument vector")
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=job.get("timeout_seconds", 300), check=False)
        if completed.returncode:
            raise DriverError(f"maintenance command exited {completed.returncode}")
        return {"ok": True, "returncode": completed.returncode}


class UnsupportedDriver:
    def _fail(self):
        raise DriverError("no M3 runtime driver is available for this endpoint; M5 adapter or remote RPC is required")
    def start(self, instance, declaration): return self._fail()
    def stop(self, instance, declaration): return self._fail()
    def status(self, instance, declaration): return {"alive": False}
    def is_ready(self, instance, declaration, readiness): return False
    def run_maintenance(self, instance, declaration, job): return self._fail()
