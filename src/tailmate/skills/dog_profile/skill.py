"""Skill implementation for dog_profile."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.profile_extractor import ProfileExtractor
from tailmate.agent_runtime.models.skill_spec import SkillSpec
from tailmate.contracts.constants import (
    DOG_PROFILE_CREATE_TOOL_ID,
    DOG_PROFILE_ENRICH_TOOL_ID,
    DOG_PROFILE_SKILL_ID,
)
from tailmate.contracts.dog_profile import (
    normalize_create_dog_profile_input,
    normalize_enrich_dog_profile_input,
)
from tailmate.contracts.errors import DomainError
from tailmate.skills.base import Skill


@dataclass
class CreateDogProfileTool:
    """Create a minimal dog profile from a validated request."""

    dog_profile_db_adapter: DogProfileDBAdapter
    name: str = DOG_PROFILE_CREATE_TOOL_ID

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = normalize_create_dog_profile_input(payload)
        except Exception as exc:
            raise DomainError("Invalid dog_profile create payload.") from exc
        result = self.dog_profile_db_adapter.create_profile(request)
        return result.model_dump(mode="json")


@dataclass
class EnrichDogProfileTool:
    """Extract and persist incremental dog profile updates from a message."""

    dog_profile_db_adapter: DogProfileDBAdapter
    profile_extractor: ProfileExtractor
    name: str = DOG_PROFILE_ENRICH_TOOL_ID

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = normalize_enrich_dog_profile_input(payload)
        except Exception as exc:
            raise DomainError("Invalid dog_profile enrich payload.") from exc

        current_profile = request.current_profile
        if current_profile is None:
            current_profile = self.dog_profile_db_adapter.load_profile(
                request.dog_id,
                requesting_user_id=request.requesting_user_id,
            )
        if current_profile is None:
            raise DomainError(f"Dog profile '{request.dog_id}' does not exist.")

        extraction_result = self.profile_extractor.extract(request.user_message, current_profile)
        result = self.dog_profile_db_adapter.enrich_profile(
            request.model_copy(update={"current_profile": current_profile}),
            extraction_result,
        )
        return result.model_dump(mode="json")


def build_dog_profile_skill(
    *,
    dog_profile_db_adapter: DogProfileDBAdapter,
    profile_extractor: ProfileExtractor,
) -> Skill:
    """Build the registered dog_profile skill."""

    create_tool = CreateDogProfileTool(dog_profile_db_adapter=dog_profile_db_adapter)
    enrich_tool = EnrichDogProfileTool(
        dog_profile_db_adapter=dog_profile_db_adapter,
        profile_extractor=profile_extractor,
    )
    return Skill(
        spec=SkillSpec(
            skill_id=DOG_PROFILE_SKILL_ID,
            description=(
                "Create a minimal dog profile from a name and silently enrich it over time "
                "from later user messages."
            ),
            tool_ids=[create_tool.name, enrich_tool.name],
        ),
        tools=[create_tool, enrich_tool],
    )
