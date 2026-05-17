"""EnrichConfirmStep — terminal confirmation for plain enrich turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.turn_messages import build_enrich_confirmation
from tailmate.contracts.constants import DOG_PROFILE_ENRICH_TOOL_ID


@dataclass
class EnrichConfirmStep:
    """Terminal step: emits an enrich confirmation (no KB answer needed)."""

    step_id: ClassVar[str] = "enrich_confirm"

    def run(self, ctx: TurnContext) -> None:
        if (
            ctx.dog_profile_result is None
            or ctx.dog_profile_result.outcome != "enrich"
        ):
            return
        ctx.response = build_enrich_confirmation(
            locale=ctx.locale,
            updated_fields=ctx.dog_profile_result.updated_fields,
            raw_note_present=ctx.dog_profile_result.raw_note_present,
        )
        ctx.skill_id = DOG_PROFILE_ENRICH_TOOL_ID
        ctx.source = "skill:dog_profile:enrich"
        ctx.is_terminal = True
