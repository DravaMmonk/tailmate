"""Agent Engine aware session adapter."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.adapters.database.conversation_store import DatabaseConversationStore
from tailmate.agent_runtime.models.session_context import SessionContext


@dataclass
class AgentEngineSessionStore:
    """Bridges runtime session identifiers to database-backed state."""

    conversation_store: DatabaseConversationStore

    def load(self, session_id: str) -> SessionContext:
        return self.conversation_store.load(session_id)

    def save(self, context: SessionContext) -> None:
        self.conversation_store.save(context)
