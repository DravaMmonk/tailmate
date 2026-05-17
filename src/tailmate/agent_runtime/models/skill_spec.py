"""Declarative skill specification."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillSpec:
    """Defines how a skill attaches to the root agent."""

    skill_id: str
    description: str
    tool_ids: list[str] = field(default_factory=list)
    depends_on: tuple[str, ...] = field(default_factory=tuple)
