"""FallbackStep — unconditional catch-all, always terminal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.turn_messages import (
    build_fallback_message,
    classify_fallback_reason,
)


@dataclass
class FallbackStep:
    """Terminal step: classifies and emits a fallback message for unhandled turns."""

    step_id: ClassVar[str] = "fallback"

    def run(self, ctx: TurnContext) -> None:
        fallback_reason = classify_fallback_reason(
            ctx.message,
            ctx.locale,
            context_attributes=ctx.session.attributes,
            turns=ctx.session.turns,
        )
        ctx.response = build_fallback_message(
            locale=ctx.locale,
            reason=fallback_reason,
        )
        ctx.source = "fallback"
        ctx.fallback_reason = fallback_reason
        ctx.is_terminal = True
