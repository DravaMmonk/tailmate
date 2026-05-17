"""CreateConfirmStep — terminal response for outcome=create."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.turn_messages import build_create_confirmation
from tailmate.contracts.constants import DOG_PROFILE_CREATE_TOOL_ID


@dataclass
class CreateConfirmStep:
    """Terminal step: emits a create confirmation when a profile was just created."""

    step_id: ClassVar[str] = "create_confirm"

    def run(self, ctx: TurnContext) -> None:
        if (
            ctx.dog_profile_result is None
            or ctx.dog_profile_result.outcome != "create"
            or ctx.dog_profile_result.created_name is None
        ):
            return
        ctx.response = build_create_confirmation(
            locale=ctx.locale,
            name=ctx.dog_profile_result.created_name,
        )
        ctx.skill_id = DOG_PROFILE_CREATE_TOOL_ID
        ctx.source = "skill:dog_profile:create"
        ctx.is_terminal = True
