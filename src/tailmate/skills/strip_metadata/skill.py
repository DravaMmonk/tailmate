"""Media privacy skill that strips EXIF and container metadata before storage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tailmate.agent_runtime.models.skill_spec import SkillSpec
from tailmate.agent_runtime.ports.sanitized_media_store import SanitizedMediaStore
from tailmate.contracts.constants import STRIP_METADATA_SKILL_ID, STRIP_METADATA_TOOL_ID
from tailmate.contracts.errors import DomainError
from tailmate.contracts.types import normalize_strip_metadata_request
from tailmate.skills.base import Skill


@dataclass
class StripMetadataTool:
    """Focused tool wrapper around the media-sanitization port."""

    sanitized_media_store: SanitizedMediaStore
    name: str = STRIP_METADATA_TOOL_ID

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            request = normalize_strip_metadata_request(payload)
        except ValueError as exc:
            raise DomainError("Invalid strip_metadata request payload.") from exc
        return dict(self.sanitized_media_store.strip_and_store(request))


def build_strip_metadata_skill(sanitized_media_store: SanitizedMediaStore) -> Skill:
    """Build the registered strip_metadata skill."""

    tool = StripMetadataTool(sanitized_media_store=sanitized_media_store)
    return Skill(
        spec=SkillSpec(
            skill_id=STRIP_METADATA_SKILL_ID,
            description=(
                "Strip GPS coordinates, device identifiers, timestamps, and other embedded "
                "metadata from uploaded media before anything is stored or analyzed."
            ),
            tool_ids=[tool.name],
        ),
        tools=[tool],
    )
