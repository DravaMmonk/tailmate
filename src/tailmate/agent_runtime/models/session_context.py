"""Persisted conversation context model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SessionContext:
    """Database-backed conversation state used as the system SSOT."""

    session_id: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
