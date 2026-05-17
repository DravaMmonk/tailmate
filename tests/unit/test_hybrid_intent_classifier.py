from __future__ import annotations

from tailmate.agent_runtime.pipeline.turn_context import IntentClassification, TurnContext
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.services.hybrid_intent_classifier import HybridIntentClassifier
from tailmate.skills.registry import InMemorySkillRegistry
from tailmate.agent_runtime.pipeline.skills import register_standard_runtime_skills


class FakeClassifier:
    def __init__(self, result: IntentClassification, *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def classify(self, ctx: TurnContext) -> IntentClassification:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def _build_context(message: str = "How old is Buddy?") -> TurnContext:
    return TurnContext(
        session=SessionContext(session_id="session-1"),
        session_id="session-1",
        message=message,
        locale="en-AU",
        locale_resolution=None,
        request_metadata={},
        strip_request=None,
    )


def _build_registry() -> InMemorySkillRegistry:
    registry = InMemorySkillRegistry()
    register_standard_runtime_skills(registry)
    return registry


def test_hybrid_classifier_keeps_high_confidence_rule_match_without_llm() -> None:
    registry = _build_registry()
    rule_classifier = FakeClassifier(
        IntentClassification(
            intent="known",
            matched_skills=("dog_profile:recall",),
            confidence=1.0,
            reasoning="Rule matched recall.",
        )
    )
    llm_classifier = FakeClassifier(
        IntentClassification(
            intent="known",
            matched_skills=("knowledge_base",),
            confidence=0.99,
            reasoning="LLM would disagree.",
        )
    )

    result = HybridIntentClassifier(
        skill_registry=registry,
        rule_classifier=rule_classifier,
        llm_classifier=llm_classifier,
    ).classify(_build_context())

    assert result.matched_skills == ("dog_profile:recall",)
    assert rule_classifier.calls == 1
    assert llm_classifier.calls == 0


def test_hybrid_classifier_uses_llm_for_open_rule_result_when_confident() -> None:
    registry = _build_registry()
    rule_classifier = FakeClassifier(
        IntentClassification(
            intent="open",
            matched_skills=("knowledge_base",),
            confidence=0.0,
            reasoning="No rule match.",
        )
    )
    llm_classifier = FakeClassifier(
        IntentClassification(
            intent="known",
            matched_skills=("dog_profile:recall",),
            confidence=0.88,
            reasoning="LLM recognized recall phrasing.",
        )
    )

    result = HybridIntentClassifier(
        skill_registry=registry,
        rule_classifier=rule_classifier,
        llm_classifier=llm_classifier,
        confidence_threshold=0.7,
    ).classify(_build_context("你知道关于Buddy的哪些信息"))

    assert result.matched_skills == ("dog_profile:recall",)
    assert result.reasoning == "LLM recognized recall phrasing."
    assert llm_classifier.calls == 1


def test_hybrid_classifier_falls_back_to_rule_when_llm_confidence_is_low() -> None:
    registry = _build_registry()
    rule_classifier = FakeClassifier(
        IntentClassification(
            intent="open",
            matched_skills=("knowledge_base",),
            confidence=0.0,
            reasoning="No rule match.",
        )
    )
    llm_classifier = FakeClassifier(
        IntentClassification(
            intent="known",
            matched_skills=("dog_profile:recall",),
            confidence=0.41,
            reasoning="Low-confidence guess.",
        )
    )

    result = HybridIntentClassifier(
        skill_registry=registry,
        rule_classifier=rule_classifier,
        llm_classifier=llm_classifier,
        confidence_threshold=0.7,
    ).classify(_build_context())

    assert result.intent == "open"
    assert result.matched_skills == ("knowledge_base",)


def test_hybrid_classifier_falls_back_to_rule_when_llm_errors() -> None:
    registry = _build_registry()
    rule_classifier = FakeClassifier(
        IntentClassification(
            intent="open",
            matched_skills=("knowledge_base",),
            confidence=0.0,
            reasoning="No rule match.",
        )
    )
    llm_classifier = FakeClassifier(
        IntentClassification(intent="open", matched_skills=()),
        error=RuntimeError("boom"),
    )

    result = HybridIntentClassifier(
        skill_registry=registry,
        rule_classifier=rule_classifier,
        llm_classifier=llm_classifier,
    ).classify(_build_context())

    assert result.intent == "open"
    assert result.matched_skills == ("knowledge_base",)


def test_hybrid_classifier_keeps_multi_skill_open_matches() -> None:
    registry = _build_registry()
    rule_classifier = FakeClassifier(
        IntentClassification(
            intent="open",
            matched_skills=("knowledge_base",),
            confidence=0.0,
            reasoning="No rule match.",
        )
    )
    llm_classifier = FakeClassifier(
        IntentClassification(
            intent="open",
            matched_skills=("dog_profile:enrich", "knowledge_base"),
            confidence=0.83,
            reasoning="The user both updates context and asks a question.",
        )
    )

    result = HybridIntentClassifier(
        skill_registry=registry,
        rule_classifier=rule_classifier,
        llm_classifier=llm_classifier,
    ).classify(_build_context("Buddy has been coughing, should I be worried?"))

    assert result.intent == "open"
    assert result.matched_skills == ("dog_profile:enrich", "knowledge_base")
