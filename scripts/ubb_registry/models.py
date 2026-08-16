"""Immutable views of validated registry manifests."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Service:
    id: str
    document: dict[str, Any]
    source: Path

    @property
    def type(self) -> str:
        return self.document["service"]["type"]

    @property
    def title(self) -> str:
        return self.document["service"]["title"]

    @property
    def endpoint_id(self) -> str:
        return self.document["endpoint"]

    @property
    def integration_id(self) -> str | None:
        return self.document.get("integration")

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.document)


@dataclass(frozen=True)
class Endpoint:
    id: str
    document: dict[str, Any]
    source: Path

    @property
    def type(self) -> str:
        return self.document["type"]

    def normalized(self) -> dict[str, Any]:
        result = {key: copy.deepcopy(value) for key, value in self.document.items()
                  if key not in ("kind", "schema_version")}
        if result["type"] == "supervisor":
            result["type"] = "remote_supervisor"
        host = result.get("host")
        local_host = host in (None, "localhost", "127.0.0.1", "::1")
        result["location"] = "local" if self.type in ("local_process", "serial") or (self.type in ("tcp","udp") and local_host) else "remote"
        return result

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.document)


@dataclass(frozen=True)
class Integration:
    id: str
    document: dict[str, Any]
    source: Path

    @property
    def runtime(self) -> str:
        return self.document["runtime"]

    @property
    def target(self) -> str:
        return self.document["target"]

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self.document)
