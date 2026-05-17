"""Runtime request context propagated through the agent execution path."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RuntimeRequestContext:
    """Per-request context made available to the runtime and skills."""

    session_id: str
    metadata: dict[str, Any] = field(default_factory=dict)
    dog_id: str | None = None
    user_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None


_current_context: ContextVar[RuntimeRequestContext | None] = ContextVar(
    "tailmate_current_context",
    default=None,
)


def set_current_context(context: RuntimeRequestContext) -> Token[RuntimeRequestContext | None]:
    """Install the request context for the current execution."""

    return _current_context.set(context)


def reset_current_context(token: Token[RuntimeRequestContext | None]) -> None:
    """Restore the previous request context."""

    _current_context.reset(token)


def get_current_context() -> RuntimeRequestContext | None:
    """Return the current request context if one is active."""

    return _current_context.get()


def get_current_dog_id() -> str | None:
    """Return the active dog id for the current request."""

    context = get_current_context()
    if context is None:
        return None
    return context.dog_id


def get_current_user_id() -> str | None:
    """Return the verified user id for the current request."""

    context = get_current_context()
    if context is None:
        return None
    return context.user_id


def get_current_request_id() -> str | None:
    """Return the active request id for the current request."""

    context = get_current_context()
    if context is None:
        return None
    return context.request_id


def get_current_trace_id() -> str | None:
    """Return the active trace id for the current request."""

    context = get_current_context()
    if context is None:
        return None
    return context.trace_id
