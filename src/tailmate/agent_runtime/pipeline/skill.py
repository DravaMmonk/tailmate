"""Self-describing runtime skill contract for orchestration steps."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from tailmate.agent_runtime.pipeline.turn_context import AssistantTurn, SkillExecutionResult, TurnContext


@dataclass(frozen=True)
class IntentMatch:
    """Intent decision produced by one runtime skill."""

    intent: Literal["known", "open"]
    priority: int = 0


class Skill(Protocol):
    """Runtime skill contract consumed by orchestration pipeline steps."""

    skill_id: str
    routing_description: str
    depends_on: tuple[str, ...]

    def classify(self, ctx: TurnContext) -> IntentMatch | None:
        """Return an intent match when the skill should participate in this turn."""

    def execute(self, ctx: TurnContext) -> SkillExecutionResult:
        """Execute the runtime skill for the current turn."""

    def apply_context(self, ctx: TurnContext, result: SkillExecutionResult) -> None:
        """Persist any skill-owned side effects back onto the shared turn context."""

    def assemble(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        """Build a response turn for one execution result, or return ``None``."""

    def assemble_open_intent_fallback(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        """Build a deterministic open-intent fallback turn after LLM fallback fails."""
