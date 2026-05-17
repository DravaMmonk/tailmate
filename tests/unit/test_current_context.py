from __future__ import annotations

from tailmate.agent_runtime.current_context import (
    RuntimeRequestContext,
    get_current_context,
    get_current_dog_id,
    get_current_trace_id,
    get_current_user_id,
    reset_current_context,
    set_current_context,
)


def test_current_context_exposes_dog_id() -> None:
    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-1",
            metadata={"dog_id": "dog-123"},
            dog_id="dog-123",
            user_id="user-123",
            trace_id="trace-123",
        )
    )

    try:
        assert get_current_context() is not None
        assert get_current_dog_id() == "dog-123"
        assert get_current_trace_id() == "trace-123"
        assert get_current_user_id() == "user-123"
    finally:
        reset_current_context(token)

    assert get_current_context() is None
