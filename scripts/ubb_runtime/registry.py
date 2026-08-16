"""Deterministic built-in runtime adapter registry."""
from __future__ import annotations

from .adapters import (FSUAEAdapter, ProcessAdapter, QEMUAdapter, SIMHAdapter,
                       UnsupportedAdapter, VICEAdapter)
from .errors import UnknownRuntimeError


class RuntimeAdapterRegistry:
    def __init__(self, adapters=None):
        self._adapters = dict(adapters or {})

    @classmethod
    def defaults(cls):
        return cls({"native": ProcessAdapter(), "fs_uae": FSUAEAdapter(),
                    "vice": VICEAdapter(), "qemu": QEMUAdapter(), "simh": SIMHAdapter(),
                    "dos": UnsupportedAdapter("dos"), "mame": UnsupportedAdapter("mame"),
                    "hatari": UnsupportedAdapter("hatari"), "remote": UnsupportedAdapter("remote")})

    def get(self, runtime):
        try: return self._adapters[runtime]
        except KeyError as exc: raise UnknownRuntimeError(f"unknown runtime adapter: {runtime}") from exc

    def names(self): return tuple(sorted(self._adapters))

    def describe(self):
        return [{"runtime": name, "supported": not isinstance(self._adapters[name], UnsupportedAdapter),
                 "adapter": type(self._adapters[name]).__name__} for name in self.names()]
