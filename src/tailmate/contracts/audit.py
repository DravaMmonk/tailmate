"""Audit logging contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AuditLogger(ABC):
    """Persistence boundary for entity mutation audit trails."""

    @abstractmethod
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
        """Persist a single audit event."""
