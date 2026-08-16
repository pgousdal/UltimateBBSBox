"""Structured runtime operation results."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuntimeStatus:
    alive: bool
    pid: int | None = None
    exit_code: int | None = None
    identity_verified: bool = False
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self):
        return {"alive": self.alive, "pid": self.pid, "exit_code": self.exit_code,
                "identity_verified": self.identity_verified, "diagnostics": dict(self.diagnostics)}


@dataclass(frozen=True)
class RuntimeStartResult:
    started: bool
    pid: int | None
    command: tuple[str, ...]
    already_running: bool = False

    def to_dict(self):
        return {"started": self.started, "pid": self.pid, "command": list(self.command),
                "already_running": self.already_running}


@dataclass(frozen=True)
class RuntimeStopResult:
    stopped: bool
    forced: bool = False
    exit_code: int | None = None

    def to_dict(self):
        return {"stopped": self.stopped, "forced": self.forced, "exit_code": self.exit_code}


@dataclass(frozen=True)
class RuntimeReadinessResult:
    ready: bool
    strategy: str
    diagnostic: str | None = None

    def to_dict(self):
        return {"ready": self.ready, "strategy": self.strategy, "diagnostic": self.diagnostic}
