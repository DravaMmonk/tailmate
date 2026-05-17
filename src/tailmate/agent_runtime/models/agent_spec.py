"""Declarative agent specification."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AgentSpec:
    """Defines the shape of the root agent."""

    agent_id: str
    description: str
    model_name: str
    skill_ids: list[str] = field(default_factory=list)
