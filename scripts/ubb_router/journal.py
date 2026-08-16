"""Append-only metadata-only session event journal."""
from __future__ import annotations

import json
import os
import pathlib
import threading


class SessionJournal:
    def __init__(self, root):
        self.root = pathlib.Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o750)
        self.path = self.root / "events.jsonl"
        self._lock = threading.Lock()

    def append(self, event: dict) -> None:
        allowed = ("timestamp", "session_id", "target_service", "origin_service", "event_type",
                   "old_state", "new_state", "endpoint_id", "termination_reason", "error")
        safe = {key: event[key] for key in allowed if event.get(key) is not None}
        data = (json.dumps(safe, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with self._lock:
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o640)
            try:
                os.write(fd, data); os.fsync(fd)
            finally:
                os.close(fd)
