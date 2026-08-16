"""Injectable wall/monotonic clocks."""
from __future__ import annotations

import datetime as dt
import time


class SystemClock:
    def now(self) -> dt.datetime:
        return dt.datetime.now().astimezone()

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FakeClock:
    def __init__(self, current: dt.datetime | None = None):
        self.current = current or dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        if self.current.tzinfo is None:
            raise ValueError("FakeClock requires a timezone-aware timestamp")
        self.elapsed = 0.0

    def now(self) -> dt.datetime:
        return self.current

    def monotonic(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.advance(seconds)

    def advance(self, seconds: float) -> None:
        self.elapsed += seconds
        self.current += dt.timedelta(seconds=seconds)
