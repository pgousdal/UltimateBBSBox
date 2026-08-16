"""Route requests, terminal capabilities, and transient sessions."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .errors import RouterError


class RouteType(str, Enum):
    DIRECT = "direct"
    VIA_SERVICE = "via_service"


class HandoffMode(str, Enum):
    REPLACE = "replace"
    RETURN_TO_ORIGIN = "return_to_origin"


@dataclass(frozen=True)
class TerminalCapabilities:
    encoding: str = "utf-8"
    display: str = "raw"
    width: int = 80
    height: int = 24
    baud: int | None = None
    binary_safe: bool = True
    newline: str = "preserve"
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.encoding or not self.display or self.width < 1 or self.height < 1:
            raise RouterError("terminal encoding/display must be non-empty and dimensions positive")
        if self.baud is not None and self.baud < 1:
            raise RouterError("terminal baud must be positive")

    def to_dict(self) -> dict:
        return {"encoding": self.encoding, "display": self.display, "width": self.width,
                "height": self.height, "baud": self.baud, "binary_safe": self.binary_safe,
                "newline": self.newline, "extensions": copy.deepcopy(self.extensions)}


@dataclass(frozen=True)
class RouteRequest:
    target_service: str
    route_type: RouteType = RouteType.DIRECT
    origin_service: str | None = None
    terminal: TerminalCapabilities = field(default_factory=TerminalCapabilities)
    caller_metadata: dict[str, Any] = field(default_factory=dict)


class SessionState(str, Enum):
    CREATED = "created"
    AUTHORIZING = "authorizing"
    ACQUIRING = "acquiring"
    CONNECTING = "connecting"
    ACTIVE = "active"
    HANDING_OFF = "handing_off"
    CLOSING = "closing"
    CLOSED = "closed"
    FAILED = "failed"


@dataclass
class Session:
    id: str
    target_service: str
    origin_service: str | None
    route_type: RouteType
    created_at: str
    terminal: TerminalCapabilities
    caller_metadata: dict[str, Any]
    state: SessionState = SessionState.CREATED
    lifecycle_session_id: str | None = None
    endpoint: dict | None = None
    termination_reason: str | None = None
    parent_session_id: str | None = None
    handoff_mode: HandoffMode | None = None
    return_to_origin: bool = False
    stream: Any = field(default=None, repr=False, compare=False)
    hold_released: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "target_service": self.target_service,
                "origin_service": self.origin_service, "route_type": self.route_type.value,
                "created_at": self.created_at, "terminal": self.terminal.to_dict(),
                "caller_metadata": copy.deepcopy(self.caller_metadata), "state": self.state.value,
                "lifecycle_session_id": self.lifecycle_session_id,
                "endpoint": copy.deepcopy(self.endpoint), "termination_reason": self.termination_reason,
                "parent_session_id": self.parent_session_id,
                "handoff_mode": self.handoff_mode.value if self.handoff_mode else None,
                "return_to_origin": self.return_to_origin}
