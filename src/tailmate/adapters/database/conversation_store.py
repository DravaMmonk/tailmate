"""Database-backed conversation state adapter."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import conversation_sessions
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.contracts.errors import AdapterError
from tailmate.tracing import start_span
from sqlalchemy import delete as sql_delete, select, update


logger = logging.getLogger(__name__)


@dataclass
class DatabaseConversationStore:
    """SSOT adapter for persisted conversation state."""

    engine_factory: DatabaseEngineFactory

    @staticmethod
    def _build_context_from_row(row: dict[str, object]) -> SessionContext:
        """Normalize one persisted row into the canonical session context."""

        return SessionContext(
            session_id=str(row["session_id"]),
            turns=list(row["turns"]),
            attributes=dict(row["attributes"]),
        )

    def load_optional(self, session_id: str) -> SessionContext | None:
        """Load a session when it exists, otherwise return `None`."""

        with start_span(
            "db.conversation.load_optional",
            attributes={"db.system": "postgresql", "db.operation": "select"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    row = connection.execute(
                        select(
                            conversation_sessions.c.session_id,
                            conversation_sessions.c.turns,
                            conversation_sessions.c.attributes,
                        ).where(conversation_sessions.c.session_id == session_id)
                    ).mappings().first()
            except Exception as exc:
                logger.exception(
                    "conversation_store.load_optional failed for session_id=%s with %s: %s",
                    session_id,
                    type(exc).__name__,
                    exc,
                )
                raise AdapterError(f"Failed to load conversation session '{session_id}'.") from exc
            finally:
                engine.dispose()

        if row is None:
            return None
        return self._build_context_from_row(dict(row))

    def load(self, session_id: str) -> SessionContext:
        context = self.load_optional(session_id)
        if context is None:
            return SessionContext(session_id=session_id)
        return context

    def save(self, context: SessionContext) -> None:
        with start_span(
            "db.conversation.save",
            attributes={"db.system": "postgresql", "db.operation": "upsert"},
        ):
            engine = self.engine_factory.create()
            payload = {
                "session_id": context.session_id,
                "turns": context.turns,
                "attributes": context.attributes,
            }
            try:
                with engine.begin() as connection:
                    existing = connection.execute(
                        select(conversation_sessions.c.session_id).where(
                            conversation_sessions.c.session_id == context.session_id
                        )
                    ).first()
                    if existing is None:
                        connection.execute(conversation_sessions.insert().values(**payload))
                    else:
                        connection.execute(
                            update(conversation_sessions)
                            .where(conversation_sessions.c.session_id == context.session_id)
                            .values(turns=context.turns, attributes=context.attributes)
                        )
            except Exception as exc:
                logger.exception(
                    "conversation_store.save failed for session_id=%s with %s: %s",
                    context.session_id,
                    type(exc).__name__,
                    exc,
                )
                raise AdapterError(
                    f"Failed to save conversation session '{context.session_id}'."
                ) from exc
            finally:
                engine.dispose()

    def delete(self, session_id: str) -> bool:
        """Delete one persisted session and report whether it existed."""

        with start_span(
            "db.conversation.delete",
            attributes={"db.system": "postgresql", "db.operation": "delete"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    result = connection.execute(
                        sql_delete(conversation_sessions).where(
                            conversation_sessions.c.session_id == session_id
                        )
                    )
            except Exception as exc:
                logger.exception(
                    "conversation_store.delete failed for session_id=%s with %s: %s",
                    session_id,
                    type(exc).__name__,
                    exc,
                )
                raise AdapterError(
                    f"Failed to delete conversation session '{session_id}'."
                ) from exc
            finally:
                engine.dispose()

        deleted_rows = result.rowcount or 0
        return deleted_rows > 0

    def load_history(self, session_id: str) -> list[dict]:
        """Load the stored turn history for a session."""

        return self.load(session_id).turns

    def save_turn(self, session_id: str, turn: dict) -> SessionContext:
        """Append a single turn and persist it immediately."""

        context = self.load(session_id)
        context.turns.append(turn)
        self.save(context)
        return context
