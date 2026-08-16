"""Privacy-safe JSONL audit persistence."""

import datetime
import json
import os
import pathlib
import secrets
import threading


class AuditLog:
    """Append complete audit records without in-process write races."""

    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        self._lock = threading.RLock()

    def append(
        self,
        actor,
        role,
        action,
        target,
        result,
        source="web",
        message="",
        request_id=None,
        remote=None,
    ):
        """Persist one terminal request outcome as one complete JSON line."""
        record = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "actor": actor,
            "role": role,
            "action": action,
            "target": target,
            "result": result,
            "source": source,
            "message": message[:500],
            "request_id": request_id or secrets.token_urlsafe(12),
        }
        if remote:
            record["remote"] = remote

        payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
        with self._lock:
            fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o640)
            try:
                offset = 0
                while offset < len(payload):
                    offset += os.write(fd, payload[offset:])
                os.fsync(fd)
            finally:
                os.close(fd)
        return record

    def read(self, limit=100):
        with self._lock:
            try:
                lines = self.path.read_text().splitlines()[-limit:]
            except FileNotFoundError:
                return []
        return [json.loads(line) for line in reversed(lines) if line]
