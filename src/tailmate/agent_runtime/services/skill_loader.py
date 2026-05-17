"""Skill attachment service."""

from __future__ import annotations

from tailmate.agent_runtime.ports.skill_registry import SkillRegistry


def load_skill_ids(registry: SkillRegistry) -> list[str]:
    """Returns the registered skill identifiers for assembly."""

    return [skill.spec.skill_id for skill in registry.all()]
