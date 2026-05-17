"""Base skill contract."""

from __future__ import annotations

from dataclasses import dataclass, field

from tailmate.agent_runtime.models.skill_spec import SkillSpec
from tailmate.agent_runtime.ports.tool import Tool


@dataclass(frozen=True)
class Skill:
    """Required shape for every attachable capability."""

    spec: SkillSpec
    tools: list[Tool] = field(default_factory=list)
