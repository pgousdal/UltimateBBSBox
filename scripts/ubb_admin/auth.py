"""Local admin credentials, bounded login throttling, and web sessions."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import threading
import time
from collections import OrderedDict
from typing import Callable

ROLES = {"viewer": 0, "operator": 1, "administrator": 2}
_DUMMY_HASH = "pbkdf2_sha256$240000$ZHVtbXlzYWx0MTIzNDU2Nzg5MA==$ZHVtbXl2YWx1ZQ=="


class LoginThrottle:
    """Temporary username/source backoff with bounded in-memory state."""

    def __init__(self, clock: Callable[[], float] = time.time, max_entries: int = 4096):
        self.clock = clock
        self.max_entries = max_entries
        self._entries: OrderedDict[tuple[str, str], tuple[int, float]] = OrderedDict()
        self._lock = threading.RLock()

    @staticmethod
    def _delay(failures: int) -> int:
        if failures < 4:
            return 0
        return min(60, 5 * (2 ** (failures - 4)))

    def _cleanup(self, now: float) -> None:
        expired = [key for key, (failures, retry_at) in self._entries.items() if failures >= 4 and retry_at <= now]
        for key in expired:
            self._entries.pop(key, None)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def retry_after(self, username: str, source: str) -> int:
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            retry_times = [self._entries.get((kind, value), (0, 0))[1] for kind, value in (("user", username), ("source", source))]
            return max(0, int(max(retry_times) - now + 0.999))

    def failure(self, username: str, source: str) -> int:
        now = self.clock()
        with self._lock:
            self._cleanup(now)
            delays = []
            for kind, value in (("user", username), ("source", source)):
                failures, _ = self._entries.get((kind, value), (0, now))
                failures += 1
                delay = self._delay(failures)
                self._entries[(kind, value)] = (failures, now + delay)
                self._entries.move_to_end((kind, value))
                delays.append(delay)
            self._cleanup(now)
            return max(delays)

    def success(self, username: str, source: str) -> None:
        with self._lock:
            self._entries.pop(("user", username), None)
            self._entries.pop(("source", source), None)

    def size(self) -> int:
        with self._lock:
            self._cleanup(self.clock())
            return len(self._entries)


class AuthStore:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o750)

    def _load(self):
        try:
            return json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"users": {}}

    def _save(self, data):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
        os.chmod(self.path, 0o600)

    @staticmethod
    def hash_password(password):
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240000)
        return "pbkdf2_sha256$240000$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()

    @staticmethod
    def verify(password, encoded):
        try:
            _, iterations, salt, expected = encoded.split("$", 3)
            digest = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.urlsafe_b64decode(salt), int(iterations))
            return hmac.compare_digest(digest, base64.urlsafe_b64decode(expected))
        except Exception:
            return False

    def add(self, username, password, role="viewer"):
        if role not in ROLES:
            raise ValueError("invalid role")
        data = self._load()
        data["users"][username] = {"hash": self.hash_password(password), "role": role, "display_name": username, "enabled": True}
        self._save(data)

    def disable(self, username):
        data = self._load()
        if username not in data.get("users", {}):
            raise KeyError(username)
        data["users"][username]["enabled"] = False
        self._save(data)

    def authenticate(self, username, password):
        record = self._load().get("users", {}).get(username)
        encoded = record.get("hash", "") if record else _DUMMY_HASH
        valid = self.verify(password, encoded)
        return record if record and record.get("enabled", True) and valid else None

    def list(self):
        return [{"username": username, "role": record.get("role"), "enabled": record.get("enabled", True)} for username, record in sorted(self._load().get("users", {}).items())]


class SessionStore:
    def __init__(self, lifetime=28800):
        self.items = {}
        self.lifetime = lifetime
        self.lock = threading.RLock()

    def create(self, username, role):
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        with self.lock:
            self.items[token] = {"username": username, "role": role, "csrf": csrf, "expires": time.time() + self.lifetime}
        return token

    def get(self, token):
        with self.lock:
            session = self.items.get(token)
            if not session or session["expires"] < time.time():
                self.items.pop(token, None)
                return None
            return dict(session)

    def remove(self, token):
        with self.lock:
            self.items.pop(token, None)
