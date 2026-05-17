from __future__ import annotations

from tailmate.agent_runtime.pipeline.steps.intent_classifier_step import IntentClassifierStep
from tailmate.agent_runtime.pipeline.turn_context import IntentClassification, TurnContext
from tailmate.agent_runtime.models.session_context import SessionContext


class FakeIntentClassifier:
    def __init__(self, result: IntentClassification) -> None:
        self.result = result
        self.calls: list[TurnContext] = []

    def classify(self, ctx: TurnContext) -> IntentClassification:
        self.calls.append(ctx)
        return self.result


def test_intent_classifier_step_delegates_to_classifier_port() -> None:
    expected = IntentClassification(
        intent="known",
        matched_skills=("dog_profile:recall",),
        confidence=0.91,
        reasoning="LLM matched the active-dog recall pattern.",
    )
    classifier = FakeIntentClassifier(expected)
    ctx = TurnContext(
        session=SessionContext(session_id="session-1"),
        session_id="session-1",
        message="What breed is Buddy?",
        locale="en-AU",
        locale_resolution=None,
        request_metadata={},
        strip_request=None,
    )

    IntentClassifierStep(classifier).run(ctx)

    assert classifier.calls == [ctx]
    assert ctx.intent == expected
