"""Database-backed audit logger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import insert

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import audit_events
from tailmate.contracts.audit import AuditLogger


@dataclass
class DatabaseAuditLogger(AuditLogger):
    """Persist audit events in the shared runtime database."""

    engine_factory: DatabaseEngineFactory

    def record(
        self,
        *,
        trace_id: str,
        user_id: str,
        entity_type: str,
        entity_id: str,
        action: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                connection.execute(
                    insert(audit_events).values(
                        trace_id=trace_id,
                        user_id=user_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        action=action,
                        before=before,
                        after=after,
                    )
                )
        finally:
            engine.dispose()
