"""Atomic state storage and append-only event journaling."""
from __future__ import annotations

import json
import os
import pathlib
import tempfile
import threading

from .models import InstanceState


class StateStore:
    def __init__(self, root: pathlib.Path | str):
        self.root = pathlib.Path(root).resolve()
        self.instances = self.root / "instances"
        self.instances.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.journal = self.root / "events.jsonl"
        self._journal_lock = threading.Lock()

    def path(self, service_id: str) -> pathlib.Path:
        return self.instances / f"{service_id}.json"

    def load(self, service_id: str) -> InstanceState | None:
        path = self.path(service_id)
        try:
            return InstanceState.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return None

    def save(self, state: InstanceState) -> None:
        path = self.path(state.service_id)
        fd, temporary = tempfile.mkstemp(prefix=f".{state.service_id}.", dir=self.instances)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state.to_dict(persist=True), handle, indent=2, sort_keys=True)
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.chmod(temporary, 0o640)
            os.replace(temporary, path)
            directory_fd = os.open(self.instances, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try: os.fsync(directory_fd)
            finally: os.close(directory_fd)
        finally:
            try: os.unlink(temporary)
            except FileNotFoundError: pass

    def append_event(self, event: dict) -> None:
        line = json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n"
        with self._journal_lock:
            fd = os.open(self.journal, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o640)
            try:
                os.write(fd, line.encode("utf-8")); os.fsync(fd)
            finally:
                os.close(fd)
