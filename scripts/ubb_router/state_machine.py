"""Validated session state transitions."""
from .errors import InvalidSessionTransitionError
from .models import SessionState

TRANSITIONS = {
    SessionState.CREATED: {SessionState.AUTHORIZING, SessionState.FAILED},
    SessionState.AUTHORIZING: {SessionState.ACQUIRING, SessionState.FAILED},
    SessionState.ACQUIRING: {SessionState.CONNECTING, SessionState.FAILED},
    SessionState.CONNECTING: {SessionState.ACTIVE, SessionState.FAILED},
    SessionState.ACTIVE: {SessionState.HANDING_OFF, SessionState.CLOSING, SessionState.FAILED},
    SessionState.HANDING_OFF: {SessionState.ACTIVE, SessionState.CLOSING, SessionState.FAILED},
    SessionState.CLOSING: {SessionState.CLOSED, SessionState.FAILED},
    SessionState.FAILED: {SessionState.CLOSING, SessionState.CLOSED},
    SessionState.CLOSED: set(),
}


def validate_transition(old: SessionState, new: SessionState) -> None:
    if new not in TRANSITIONS[old]:
        raise InvalidSessionTransitionError(f"invalid session transition: {old.value} -> {new.value}")
