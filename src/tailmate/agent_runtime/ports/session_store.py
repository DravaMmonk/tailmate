"""Abstract session storage contract."""

from __future__ import annotations

from typing import Protocol

from tailmate.agent_runtime.models.session_context import SessionContext


class SessionStore(Protocol):
    """Loads and persists conversation state."""

    def load(self, session_id: str) -> SessionContext: ...

    def save(self, context: SessionContext) -> None: ...
