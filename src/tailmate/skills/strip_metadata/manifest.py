"""Manifest for the strip_metadata skill."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tailmate.contracts.constants import STRIP_METADATA_SKILL_ID
from tailmate.skills.base import Skill
from tailmate.skills.definition import SkillDefinition
from tailmate.skills.strip_metadata.skill import build_strip_metadata_skill


def build_from_dependencies(dependencies: Mapping[str, Any]) -> Skill:
    """Build strip_metadata from the resolved adapter set."""

    sanitized_media_store = dependencies["sanitized_media_store"]
    if not hasattr(sanitized_media_store, "strip_and_store"):
        raise TypeError("strip_metadata requires a SanitizedMediaStore dependency.")
    return build_strip_metadata_skill(sanitized_media_store=sanitized_media_store)


SKILL_DEFINITION = SkillDefinition(
    skill_id=STRIP_METADATA_SKILL_ID,
    name="strip_metadata",
    description=(
        "Strip GPS coordinates, device identifiers, timestamps, and other embedded "
        "metadata from uploaded media before anything is stored or analyzed."
    ),
    input_contract="tailmate.contracts.types.StripMetadataRequest",
    output_contract="tailmate.contracts.types.StripMetadataResult",
    adapter_dependencies=("sanitized_media_store",),
    factory=build_from_dependencies,
)
