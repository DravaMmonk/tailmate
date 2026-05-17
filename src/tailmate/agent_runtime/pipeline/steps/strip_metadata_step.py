"""StripMetadataStep — handles strip_metadata_request when present."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.services.turn_messages import build_strip_metadata_confirmation
from tailmate.contracts.constants import STRIP_METADATA_TOOL_ID


@dataclass
class StripMetadataStep:
    """Terminal step: renders the recorded strip-metadata execution result."""

    skill_registry: SkillRegistry
    observability: Observability
    step_id: ClassVar[str] = "strip_metadata"

    def run(self, ctx: TurnContext) -> None:
        if ctx.intent is None:
            return
        result = next(
            (
                item
                for item in ctx.skill_results
                if item.skill_id == "strip_metadata" and item.outcome == "success"
            ),
            None,
        )
        if result is None:
            return
        ctx.response = build_strip_metadata_confirmation(
            locale=ctx.locale,
            resource_uri=str(result.payload["resource_uri"]),
        )
        ctx.skill_id = STRIP_METADATA_TOOL_ID
        ctx.source = "skill:strip_metadata"
        ctx.is_terminal = True
