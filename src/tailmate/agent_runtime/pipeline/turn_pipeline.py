"""TurnPipeline — executes an ordered list of routing steps."""

from __future__ import annotations

from dataclasses import dataclass, field

from tailmate.agent_runtime.pipeline.routing_step import RoutingStep
from tailmate.agent_runtime.pipeline.turn_context import TurnContext


@dataclass
class TurnPipeline:
    """Runs steps in order, stopping at the first terminal one.

    A step signals completion by setting ``ctx.is_terminal = True``.
    Every turn is guaranteed to be handled by exactly one terminal step
    (the ``FallbackStep`` acts as the unconditional catch-all).
    """

    steps: list[RoutingStep] = field(default_factory=list)

    def execute(self, ctx: TurnContext) -> None:
        """Run the pipeline against ``ctx`` until a step sets ``ctx.is_terminal``."""
        for step in self.steps:
            step.run(ctx)
            if ctx.is_terminal:
                break
