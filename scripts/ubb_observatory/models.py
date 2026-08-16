"""Serializable, non-authoritative admin read-model records."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any

@dataclass(frozen=True)
class ServiceSummary:
    id: str
    title: str
    type: str
    integration: str | None
    runtime: str | None
    endpoint: dict[str, Any]
    policy: str | None
    recommended_policy: str | None
    state: str
    active_sessions: int
    maintenance: bool
    readiness: str
    release: str | None = None
    profile: str | None = None
    artifact: dict[str, Any] | None = None
    deployment: dict[str, Any] | None = None
    available_releases: tuple[dict[str, Any], ...] = ()
    backup: dict[str, Any] | None = None
    host_health: str = "UNKNOWN"
    attention: bool = False
    maintenance_jobs: tuple[str, ...] = ()
    health: str = "UNKNOWN"
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ActivityEvent:
    timestamp: str
    source: str
    event_type: str
    severity: str
    message: str
    service_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class Alert:
    id: str
    severity: str
    service_id: str | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    state: str = "ACTIVE"
    first_seen: str | None = None
    last_seen: str | None = None
    occurrence_count: int = 1
    cleared_at: str | None = None
    def to_dict(self): return asdict(self)

@dataclass(frozen=True)
class ObservatorySnapshot:
    services: tuple[ServiceSummary, ...]
    sessions: tuple[dict[str, Any], ...]
    activity: tuple[ActivityEvent, ...]
    alerts: tuple[Alert, ...]
    hosts: tuple[dict[str, Any], ...]
    degraded_sources: tuple[str, ...] = ()
    def to_dict(self):
        return {"services": [x.to_dict() for x in self.services], "sessions": list(self.sessions),
                "activity": [x.to_dict() for x in self.activity], "alerts": [x.to_dict() for x in self.alerts],
                "hosts": list(self.hosts), "degraded_sources": list(self.degraded_sources)}
