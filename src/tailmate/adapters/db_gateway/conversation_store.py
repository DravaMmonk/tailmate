"""Session store backed by the Cloud Run database gateway."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from tailmate.adapters.db_gateway.client import DbGatewayClient
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.contracts.errors import AdapterError


logger = logging.getLogger(__name__)


@dataclass
class GatewayConversationStore:
    """Persists conversation state through the Cloud Run gateway."""

    client: DbGatewayClient

    def load(self, session_id: str) -> SessionContext:
        try:
            payload = self.client.load_session(session_id)
        except AdapterError:
            raise
        except Exception as exc:
            logger.exception(
                "gateway_conversation_store.load failed for session_id=%s with %s: %s",
                session_id,
                type(exc).__name__,
                exc,
            )
            raise AdapterError(f"Failed to load conversation session '{session_id}'.") from exc
        return SessionContext(
            session_id=str(payload.get("session_id", session_id)),
            turns=self._coerce_turns(payload.get("turns")),
            attributes=self._coerce_attributes(payload.get("attributes")),
        )

    def save(self, context: SessionContext) -> None:
        try:
            self.client.save_session(
                context.session_id,
                turns=context.turns,
                attributes=context.attributes,
            )
        except AdapterError:
            raise
        except Exception as exc:
            logger.exception(
                "gateway_conversation_store.save failed for session_id=%s with %s: %s",
                context.session_id,
                type(exc).__name__,
                exc,
            )
            raise AdapterError(f"Failed to save conversation session '{context.session_id}'.") from exc

    def load_history(self, session_id: str) -> list[dict[str, Any]]:
        return self.load(session_id).turns

    def save_turn(self, session_id: str, turn: dict[str, Any]) -> SessionContext:
        context = self.load(session_id)
        context.turns.append(turn)
        self.save(context)
        return context

    @staticmethod
    def _coerce_turns(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _coerce_attributes(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return value
