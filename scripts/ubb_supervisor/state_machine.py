"""Validated lifecycle transition graph."""
from __future__ import annotations

from enum import Enum

from .errors import InvalidTransitionError


class LifecycleState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    RUNNING = "running"
    MAINTENANCE = "maintenance"
    STOPPING = "stopping"
    FAILED = "failed"


TRANSITIONS = {
    LifecycleState.STOPPED: {LifecycleState.STARTING},
    LifecycleState.STARTING: {LifecycleState.READY, LifecycleState.FAILED},
    LifecycleState.READY: {LifecycleState.RUNNING, LifecycleState.MAINTENANCE, LifecycleState.STOPPING, LifecycleState.FAILED},
    LifecycleState.RUNNING: {LifecycleState.MAINTENANCE, LifecycleState.STOPPING, LifecycleState.FAILED},
    LifecycleState.MAINTENANCE: {LifecycleState.RUNNING, LifecycleState.STOPPING, LifecycleState.FAILED},
    LifecycleState.STOPPING: {LifecycleState.STOPPED, LifecycleState.FAILED},
    LifecycleState.FAILED: {LifecycleState.STARTING, LifecycleState.STOPPED},
}


def validate_transition(old: LifecycleState, new: LifecycleState) -> None:
    if new not in TRANSITIONS[old]:
        raise InvalidTransitionError(f"invalid lifecycle transition: {old.value} -> {new.value}")
