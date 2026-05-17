"""ErrorStep — terminal response for swallowed skill errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.turn_messages import build_skill_error_message


@dataclass
class ErrorStep:
    """Terminal step: emits a skill-error fallback when outcome=error."""

    step_id: ClassVar[str] = "error"

    def run(self, ctx: TurnContext) -> None:
        if (
            ctx.dog_profile_result is None
            or ctx.dog_profile_result.outcome != "error"
        ):
            return
        ctx.response = build_skill_error_message(locale=ctx.locale)
        ctx.source = "fallback"
        ctx.fallback_reason = "skill_exception_swallowed"
        ctx.is_terminal = True
