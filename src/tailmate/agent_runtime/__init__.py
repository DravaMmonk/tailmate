"""Core runtime abstractions."""

from tailmate.agent_runtime.current_context import (
    RuntimeRequestContext,
    get_current_context,
    get_current_dog_id,
    reset_current_context,
    set_current_context,
)

__all__ = [
    "RuntimeRequestContext",
    "get_current_context",
    "get_current_dog_id",
    "reset_current_context",
    "set_current_context",
]
