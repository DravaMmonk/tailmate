"""Abstract skill registry contract."""

from __future__ import annotations

from typing import Protocol

from tailmate.agent_runtime.pipeline.skill import Skill as RuntimeSkill
from tailmate.skills.base import Skill


class SkillRegistry(Protocol):
    """Resolves attachable skills by identifier."""

    def register(self, skill: Skill) -> None: ...

    def all(self) -> list[Skill]: ...

    def skills(self) -> list[RuntimeSkill]: ...

    def get_skill(self, skill_id: str) -> RuntimeSkill: ...
