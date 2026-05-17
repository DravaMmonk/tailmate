"""Strip metadata skill package."""

from tailmate.skills.strip_metadata.manifest import SKILL_DEFINITION
from tailmate.skills.strip_metadata.skill import build_strip_metadata_skill

__all__ = ["SKILL_DEFINITION", "build_strip_metadata_skill"]
