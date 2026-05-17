"""Port for pre-execution intent classification."""

from __future__ import annotations

from typing import Protocol

from tailmate.agent_runtime.pipeline.turn_context import IntentClassification, TurnContext


class IntentClassifier(Protocol):
    """Produce a routing decision for one turn."""

    def classify(self, ctx: TurnContext) -> IntentClassification: ...
