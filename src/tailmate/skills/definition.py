"""Declarative skill discovery contract."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from tailmate.skills.base import Skill


SkillFactory = Callable[[Mapping[str, Any]], Skill]


@dataclass(frozen=True)
class SkillDefinition:
    """Metadata and factory contract for auto-discovered skills."""

    skill_id: str
    name: str
    description: str
    input_contract: str
    output_contract: str
    factory: SkillFactory = field(repr=False)
    adapter_dependencies: tuple[str, ...] = field(default_factory=tuple)
    default_enabled: bool = True
