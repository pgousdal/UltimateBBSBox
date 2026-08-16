"""Persistent runtime instance state."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .state_machine import LifecycleState


@dataclass
class InstanceState:
    service_id: str
    instance_id: str
    state: LifecycleState = LifecycleState.STOPPED
    holds: dict[str, int] = field(default_factory=dict)
    sessions: dict[str, str] = field(default_factory=dict)
    admin_intent: bool = False
    idle_deadline: str | None = None
    last_start_at: str | None = None
    last_stop_at: str | None = None
    last_failure: str | None = None
    restart_times: list[str] = field(default_factory=list)
    next_restart_at: str | None = None
    restart_exhausted: bool = False
    maintenance_results: dict[str, dict] = field(default_factory=dict)
    schedule_last_run: dict[str, str] = field(default_factory=dict)
    runtime: dict = field(default_factory=dict)

    def active_holds(self) -> int:
        return sum(self.holds.values())

    def to_dict(self, persist: bool = False) -> dict:
        holds = copy.deepcopy(self.holds)
        sessions = copy.deepcopy(self.sessions)
        if persist:
            holds = {key: value for key, value in holds.items() if key in ("admin", "always_on")}
            sessions = {}
        return {
            "service_id": self.service_id, "instance_id": self.instance_id,
            "state": self.state.value, "holds": holds, "sessions": sessions,
            "active_session_count": len(self.sessions), "admin_intent": self.admin_intent,
            "idle_deadline": self.idle_deadline, "last_start_at": self.last_start_at,
            "last_stop_at": self.last_stop_at, "last_failure": self.last_failure,
            "restart_times": list(self.restart_times), "next_restart_at": self.next_restart_at,
            "restart_exhausted": self.restart_exhausted,
            "maintenance_results": copy.deepcopy(self.maintenance_results),
            "schedule_last_run": copy.deepcopy(self.schedule_last_run),
            "runtime": copy.deepcopy(self.runtime),
        }

    @classmethod
    def from_dict(cls, value: dict) -> "InstanceState":
        return cls(
            service_id=value["service_id"], instance_id=value["instance_id"],
            state=LifecycleState(value.get("state", "stopped")),
            holds={key: int(count) for key, count in value.get("holds", {}).items() if key in ("admin", "always_on")},
            sessions={}, admin_intent=bool(value.get("admin_intent", False)),
            idle_deadline=value.get("idle_deadline"), last_start_at=value.get("last_start_at"),
            last_stop_at=value.get("last_stop_at"), last_failure=value.get("last_failure"),
            restart_times=list(value.get("restart_times", [])), next_restart_at=value.get("next_restart_at"),
            restart_exhausted=bool(value.get("restart_exhausted", False)),
            maintenance_results=dict(value.get("maintenance_results", {})),
            schedule_last_run=dict(value.get("schedule_last_run", {})),
            runtime=dict(value.get("runtime", {})),
        )
