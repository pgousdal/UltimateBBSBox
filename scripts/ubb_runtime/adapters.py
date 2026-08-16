"""Product-neutral process and emulator runtime adapters."""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import pty
import re
import signal
import subprocess
import threading
import time
import tty
from typing import Protocol

from .errors import (RuntimeAdapterError, RuntimeConfigError, RuntimeStartError, RuntimeStopError,
                     RuntimeStreamError, UnsupportedRuntimeError)
from .models import RuntimeStartResult, RuntimeStatus, RuntimeStopResult
from .readiness import check_readiness
from .streams import PTYStream, PipeStream, TCPStream

ENVIRONMENT_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORBIDDEN_ENVIRONMENT = frozenset(("LD_PRELOAD", "PYTHONPATH", "PYTHONHOME"))
ALLOWED_FIELDS = frozenset(("executable", "argv", "config_file", "working_directory",
                            "environment", "inherit_environment", "pty", "stop_timeout_seconds",
                            "graceful_stop_command", "readiness", "stream"))


class RuntimeAdapter(Protocol):
    runtime_name: str
    def prepare(self, instance, config: dict) -> dict: ...
    def start(self, instance, config: dict) -> RuntimeStartResult: ...
    def stop(self, instance, config: dict) -> RuntimeStopResult: ...
    def status(self, instance, config: dict) -> RuntimeStatus: ...
    def readiness(self, instance, config: dict, strategy: dict | None = None): ...
    def open_stream(self, instance, config: dict): ...
    def cleanup(self, instance, config: dict) -> dict: ...


class ProcessAdapter:
    runtime_name = "native"

    def __init__(self):
        self._processes: dict[str, subprocess.Popen] = {}
        self._pty_masters: dict[str, int] = {}
        self._lock = threading.RLock()

    def validate_config(self, config):
        unknown = set(config) - ALLOWED_FIELDS
        if unknown:
            raise RuntimeConfigError(f"unknown runtime_config fields: {', '.join(sorted(unknown))}")
        executable = pathlib.Path(config.get("executable", ""))
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeConfigError("runtime executable must be an absolute executable file")
        argv = config.get("argv", [])
        if not isinstance(argv, list) or any(not isinstance(item, str) for item in argv):
            raise RuntimeConfigError("runtime argv must be an array of strings")
        working = pathlib.Path(config.get("working_directory", executable.parent))
        if not working.is_absolute() or not working.is_dir():
            raise RuntimeConfigError("runtime working_directory must be an existing absolute directory")
        environment = config.get("environment", {})
        inherited = config.get("inherit_environment", [])
        if len(environment) + len(inherited) > 128:
            raise RuntimeConfigError("runtime environment is limited to 128 entries")
        for key, value in environment.items():
            if not ENVIRONMENT_NAME.fullmatch(key) or key in FORBIDDEN_ENVIRONMENT or not isinstance(value, str) or len(value) > 8192:
                raise RuntimeConfigError(f"unsafe runtime environment entry: {key!r}")
        for key in inherited:
            if not ENVIRONMENT_NAME.fullmatch(key) or key in FORBIDDEN_ENVIRONMENT:
                raise RuntimeConfigError(f"unsafe inherited environment name: {key!r}")
        stream = config.get("stream")
        if stream and stream.get("type") not in ("pty", "tcp", "stdio"):
            raise RuntimeConfigError("runtime stream type must be pty, tcp, or stdio")
        if config.get("pty") and stream and stream.get("type") not in ("pty",):
            raise RuntimeConfigError("pty mode conflicts with non-PTY stream type")
        if stream and stream.get("type") == "tcp":
            if not stream.get("host") or not isinstance(stream.get("port"), int) or not 1 <= stream["port"] <= 65535:
                raise RuntimeConfigError("runtime TCP stream requires a host and port in 1..65535")
        graceful = config.get("graceful_stop_command")
        if graceful is not None and (not isinstance(graceful, list) or not graceful or any(not isinstance(item, str) for item in graceful)):
            raise RuntimeConfigError("graceful_stop_command must be a non-empty argv array")
        return {"executable": executable.resolve(), "working_directory": working.resolve()}

    def prepare(self, instance, config):
        validated = self.validate_config(config)
        instance.runtime.setdefault("adapter", self.runtime_name)
        return {"prepared": True, "runtime": self.runtime_name,
                "executable": str(validated["executable"]), "working_directory": str(validated["working_directory"])}

    def build_command(self, config):
        self.validate_config(config)
        return [str(pathlib.Path(config["executable"]).resolve()), *config.get("argv", [])]

    def _environment(self, config):
        environment = {"PATH": os.defpath, "LANG": "C.UTF-8"}
        for key in config.get("inherit_environment", []):
            if key in os.environ:
                environment[key] = os.environ[key]
        environment.update(config.get("environment", {}))
        return environment

    def _proc_identity(self, pid):
        try:
            executable = os.readlink(f"/proc/{pid}/exe")
            fields = pathlib.Path(f"/proc/{pid}/stat").read_text().split()
            return executable, fields[21]
        except (OSError, IndexError):
            return None, None

    def start(self, instance, config):
        with self._lock:
            current = self.status(instance, config)
            command = self.build_command(config)
            if current.alive:
                return RuntimeStartResult(False, current.pid, tuple(command), True)
            prepared = self.validate_config(config)
            use_pty = bool(config.get("pty") or config.get("stream", {}).get("type") == "pty")
            use_stdio = config.get("stream", {}).get("type") == "stdio"
            master = slave = None
            try:
                if use_pty:
                    master, slave = pty.openpty(); tty.setraw(slave)
                    stdin = stdout = stderr = slave
                elif use_stdio:
                    stdin = subprocess.PIPE; stdout = subprocess.PIPE; stderr = subprocess.DEVNULL
                else:
                    stdin = stdout = stderr = subprocess.DEVNULL
                process = subprocess.Popen(command, cwd=prepared["working_directory"], env=self._environment(config),
                                           stdin=stdin, stdout=stdout, stderr=stderr, start_new_session=True,
                                           close_fds=True)
            except (OSError, ValueError) as exc:
                if master is not None: os.close(master)
                raise RuntimeStartError(f"runtime start failed: {type(exc).__name__}: {exc}") from exc
            finally:
                if slave is not None: os.close(slave)
            self._processes[instance.instance_id] = process
            if master is not None: self._pty_masters[instance.instance_id] = master
            proc_executable, start_ticks = self._proc_identity(process.pid)
            instance.runtime.update({"adapter": self.runtime_name, "pid": process.pid,
                                     "process_executable": proc_executable, "process_start_ticks": start_ticks,
                                     "command_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest()})
            return RuntimeStartResult(True, process.pid, tuple(command))

    def status(self, instance, config):
        with self._lock:
            process = self._processes.get(instance.instance_id)
            if process is not None:
                code = process.poll()
                return RuntimeStatus(code is None, process.pid, code, True)
            pid = instance.runtime.get("pid")
            if not isinstance(pid, int) or pid <= 1:
                return RuntimeStatus(False)
            executable, start_ticks = self._proc_identity(pid)
            expected_executable = instance.runtime.get("process_executable")
            expected_ticks = instance.runtime.get("process_start_ticks")
            verified = bool(executable and start_ticks and expected_executable and expected_ticks and
                            executable == expected_executable and start_ticks == expected_ticks)
            return RuntimeStatus(verified, pid, identity_verified=verified,
                                 diagnostics={} if verified else {"reason": "recorded process identity cannot be proven"})

    def stop(self, instance, config):
        with self._lock:
            status = self.status(instance, config)
            if not status.alive:
                self.cleanup(instance, config)
                return RuntimeStopResult(True, False, status.exit_code)
            graceful = config.get("graceful_stop_command")
            if graceful:
                try:
                    subprocess.run(graceful, cwd=config.get("working_directory"), env=self._environment(config),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=float(config.get("stop_timeout_seconds", 5)), check=False, close_fds=True)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            try:
                os.killpg(status.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            timeout = float(config.get("stop_timeout_seconds", 5))
            deadline = time.monotonic() + timeout
            process = self._processes.get(instance.instance_id)
            while time.monotonic() < deadline:
                if process is not None:
                    code = process.poll()
                    if code is not None:
                        self.cleanup(instance, config); return RuntimeStopResult(True, False, code)
                elif not self.status(instance, config).alive:
                    self.cleanup(instance, config); return RuntimeStopResult(True)
                time.sleep(min(0.02, max(0, deadline - time.monotonic())))
            forced = True
            try: os.killpg(status.pid, signal.SIGKILL)
            except ProcessLookupError: forced = False
            code = None
            if process is not None:
                try: code = process.wait(timeout=1)
                except subprocess.TimeoutExpired as exc: raise RuntimeStopError("runtime did not exit after SIGKILL") from exc
            self.cleanup(instance, config)
            return RuntimeStopResult(True, forced, code)

    def readiness(self, instance, config, strategy=None):
        selected = strategy
        if not selected or selected.get("type") == "driver_specific":
            selected = config.get("readiness", {"type": "process_alive"})
        if selected.get("type") == "command_probe":
            selected = {**selected, "type": "command_exit_zero"}
        return check_readiness(selected, lambda: self.status(instance, config))

    def open_stream(self, instance, config):
        stream = config.get("stream", {})
        stream_type = stream.get("type", "pty" if config.get("pty") else None)
        if stream_type == "pty":
            master = self._pty_masters.get(instance.instance_id)
            if master is None: raise RuntimeStreamError("runtime has no active PTY")
            return PTYStream(os.dup(master))
        if stream_type == "stdio":
            process = self._processes.get(instance.instance_id)
            if process is None or process.stdin is None or process.stdout is None:
                raise RuntimeStreamError("runtime stdio is unavailable after process reconciliation")
            return PipeStream(os.dup(process.stdout.fileno()), os.dup(process.stdin.fileno()))
        if stream_type == "tcp":
            try:
                return TCPStream.connect(stream["host"], int(stream["port"]),
                                         float(stream.get("connect_timeout_seconds", 5)))
            except (KeyError, ValueError) as exc:
                raise RuntimeStreamError("runtime TCP stream requires valid host and port") from exc
        raise RuntimeStreamError("runtime_config.stream must select pty, stdio, or tcp")

    def run_maintenance(self, instance, config, job):
        command = job.get("command")
        if not command: raise RuntimeConfigError("maintenance requires a command argv")
        completed = subprocess.run(command, cwd=config.get("working_directory"), env=self._environment(config),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=job.get("timeout_seconds", 300), check=False, close_fds=True)
        if completed.returncode: raise RuntimeAdapterError(f"maintenance command exited {completed.returncode}")
        return {"ok": True, "returncode": completed.returncode}

    def cleanup(self, instance, config):
        with self._lock:
            process = self._processes.pop(instance.instance_id, None)
            if process is not None:
                for handle in (process.stdin, process.stdout, process.stderr):
                    if handle is not None:
                        try: handle.close()
                        except OSError: pass
            master = self._pty_masters.pop(instance.instance_id, None)
            if master is not None:
                try: os.close(master)
                except OSError: pass
            for key in ("pid", "process_executable", "process_start_ticks"):
                instance.runtime.pop(key, None)
        return {"cleaned": True}


class DOSAdapter(ProcessAdapter):
    """Generic DOS process adapter; product startup remains deployment metadata."""
    runtime_name = "dos"

    def validate_config(self, config):
        validated = super().validate_config(config)
        if config.get("dos_backend") not in (None, "dosemu2", "dosbox_x", "dosbox_staging", "qemu"):
            raise RuntimeConfigError("unsupported DOS runtime backend")
        return validated


class FSUAEAdapter(ProcessAdapter):
    runtime_name = "fs_uae"
    def build_command(self, config):
        self.validate_config(config)
        config_file = config.get("config_file")
        if not config_file or not pathlib.Path(config_file).is_file():
            raise RuntimeConfigError("fs_uae requires an existing absolute config_file")
        return [str(pathlib.Path(config["executable"]).resolve()), str(pathlib.Path(config_file).resolve()), *config.get("argv", [])]


class VICEAdapter(ProcessAdapter):
    runtime_name = "vice"


class QEMUAdapter(ProcessAdapter):
    runtime_name = "qemu"


class SIMHAdapter(ProcessAdapter):
    runtime_name = "simh"
    def build_command(self, config):
        command = super().build_command(config)
        config_file = config.get("config_file")
        if config_file:
            if not pathlib.Path(config_file).is_file(): raise RuntimeConfigError("simh config_file does not exist")
            command.append(str(pathlib.Path(config_file).resolve()))
        return command


class UnsupportedAdapter:
    def __init__(self, runtime_name): self.runtime_name = runtime_name
    def _fail(self): raise UnsupportedRuntimeError(f"runtime adapter {self.runtime_name!r} is explicitly deferred")
    def prepare(self, instance, config): return self._fail()
    def start(self, instance, config): return self._fail()
    def stop(self, instance, config): return self._fail()
    def status(self, instance, config): return RuntimeStatus(False, diagnostics={"reason": "unsupported runtime"})
    def readiness(self, instance, config, strategy=None): return self._fail()
    def open_stream(self, instance, config): return self._fail()
    def cleanup(self, instance, config): return {"cleaned": True}
