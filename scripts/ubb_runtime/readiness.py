"""One-shot generic readiness strategies polled and bounded by M3."""
from __future__ import annotations

import pathlib
import socket
import subprocess

from .models import RuntimeReadinessResult


def check_readiness(strategy: dict, status) -> RuntimeReadinessResult:
    kind = strategy.get("type", "process_alive")
    if kind == "immediate":
        return RuntimeReadinessResult(True, kind)
    if kind == "process_alive":
        alive = bool(status().alive)
        return RuntimeReadinessResult(alive, kind, None if alive else "runtime process is not alive")
    if kind == "tcp_port":
        try:
            with socket.create_connection((strategy["host"], int(strategy["port"])),
                                          timeout=float(strategy.get("timeout_seconds", 0.2))):
                return RuntimeReadinessResult(True, kind)
        except (OSError, KeyError, ValueError) as exc:
            return RuntimeReadinessResult(False, kind, type(exc).__name__)
    if kind == "file_exists":
        ready = pathlib.Path(strategy.get("path", "")).is_file()
        return RuntimeReadinessResult(ready, kind, None if ready else "configured file does not exist")
    if kind == "command_exit_zero":
        command = strategy.get("command")
        if not command:
            return RuntimeReadinessResult(False, kind, "command is required")
        try:
            completed = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, timeout=float(strategy.get("timeout_seconds", 5)),
                                       check=False, close_fds=True)
            return RuntimeReadinessResult(completed.returncode == 0, kind,
                                          None if completed.returncode == 0 else f"exit {completed.returncode}")
        except (OSError, subprocess.TimeoutExpired) as exc:
            return RuntimeReadinessResult(False, kind, type(exc).__name__)
    return RuntimeReadinessResult(False, str(kind), "unsupported readiness strategy")
