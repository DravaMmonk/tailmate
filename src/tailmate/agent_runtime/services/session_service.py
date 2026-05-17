"""Helpers for persisted conversation state."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.ports.session_store import SessionStore


@dataclass
class SessionService:
    """Thin service around the session store boundary."""

    store: SessionStore

    def load(self, session_id: str) -> SessionContext:
        return self.store.load(session_id)

    def save(self, context: SessionContext) -> None:
        self.store.save(context)
