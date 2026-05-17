"""Manifest for the dog_profile skill."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tailmate.contracts.constants import DOG_PROFILE_SKILL_ID
from tailmate.skills.base import Skill
from tailmate.skills.definition import SkillDefinition
from tailmate.skills.dog_profile.skill import build_dog_profile_skill


def build_from_dependencies(dependencies: Mapping[str, Any]) -> Skill:
    """Build the dog_profile skill from resolved adapters."""

    dog_profile_db_adapter = dependencies["dog_profile_db_adapter"]
    profile_extractor = dependencies["profile_extractor"]
    if not hasattr(dog_profile_db_adapter, "create_profile") or not hasattr(
        dog_profile_db_adapter, "enrich_profile"
    ):
        raise TypeError("dog_profile requires a DogProfileDBAdapter dependency.")
    if not hasattr(profile_extractor, "extract"):
        raise TypeError("dog_profile requires a ProfileExtractor dependency.")
    return build_dog_profile_skill(
        dog_profile_db_adapter=dog_profile_db_adapter,
        profile_extractor=profile_extractor,
    )


SKILL_DEFINITION = SkillDefinition(
    skill_id=DOG_PROFILE_SKILL_ID,
    name="dog_profile",
    description=(
        "Create a minimal dog profile from a name and enrich it in later conversations "
        "without forcing the user through a form."
    ),
    input_contract="tailmate.contracts.dog_profile.DogProfileToolRequest",
    output_contract="tailmate.contracts.dog_profile.DogProfileToolResult",
    adapter_dependencies=("dog_profile_db_adapter", "profile_extractor"),
    factory=build_from_dependencies,
    default_enabled=True,
)
