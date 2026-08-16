"""Dependency-light interval and local-time daily schedule calculation."""
from __future__ import annotations

import datetime as dt
import re

from .errors import SupervisorError

INTERVAL = re.compile(r"^every\s+(\d+)\s*([mhd])$", re.I)
DAILY = re.compile(r"^daily(?:\s+at)?\s+(\d{1,2}):(\d{2})$", re.I)


def parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_due(schedule: str, now: dt.datetime, last_run: str | None) -> bool:
    if now.tzinfo is None:
        raise SupervisorError("scheduler requires timezone-aware timestamps")
    previous = parse_timestamp(last_run)
    match = INTERVAL.fullmatch(schedule.strip())
    if match:
        count = int(match.group(1))
        if count < 1:
            raise SupervisorError(f"invalid interval schedule: {schedule}")
        seconds = count * {"m": 60, "h": 3600, "d": 86400}[match.group(2).lower()]
        return previous is None or now >= previous + dt.timedelta(seconds=seconds)
    match = DAILY.fullmatch(schedule.strip())
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            raise SupervisorError(f"invalid daily schedule: {schedule}")
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return now >= scheduled and (previous is None or previous < scheduled)
    raise SupervisorError(f"unsupported maintenance schedule: {schedule!r}")
