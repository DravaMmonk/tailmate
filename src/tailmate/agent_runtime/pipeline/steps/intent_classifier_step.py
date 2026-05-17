"""IntentClassifierStep — generic first-stage routing classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.ports.intent_classifier import IntentClassifier
from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.metrics import record_intent_classification, resolve_classifier_metric_name


@dataclass
class IntentClassifierStep:
    """Classify one turn before downstream steps decide what to execute."""

    classifier: IntentClassifier
    step_id: ClassVar[str] = "intent_classifier"

    def run(self, ctx: TurnContext) -> None:
        ctx.intent = self.classifier.classify(ctx)
        record_intent_classification(
            intent=ctx.intent.intent,
            classifier=resolve_classifier_metric_name(self.classifier),
        )
