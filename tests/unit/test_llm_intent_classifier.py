from __future__ import annotations

import pytest

from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.llm_intent_classifier import LLMIntentClassifier
from tailmate.agent_runtime.pipeline.skills import register_standard_runtime_skills
from tailmate.metrics import render_prometheus_metrics, reset_metrics_registry
from tailmate.skills.registry import InMemorySkillRegistry
from tailmate.contracts.errors import AdapterError


class FakeModelResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModel:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []
        self.request_options: list[dict[str, object] | None] = []

    def generate_content(
        self,
        prompt: str,
        generation_config,
        request_options=None,
    ) -> FakeModelResponse:
        self.prompts.append(prompt)
        self.request_options.append(request_options)
        return FakeModelResponse(self.text)


def _build_classifier(payload: str) -> tuple[LLMIntentClassifier, FakeModel]:
    reset_metrics_registry()
    registry = InMemorySkillRegistry()
    register_standard_runtime_skills(registry)
    model = FakeModel(payload)
    classifier = LLMIntentClassifier(
        skill_registry=registry,
        model_name="gemini-test",
        project_id="test-project",
        location="global",
        initializer=lambda **kwargs: None,
        model_factory=lambda _model_name: model,
    )
    return classifier, model


def _build_context(message: str = "What breed is Buddy?") -> TurnContext:
    return TurnContext(
        session=SessionContext(session_id="session-1"),
        session_id="session-1",
        message=message,
        locale="en-AU",
        locale_resolution=None,
        request_metadata={},
        strip_request=None,
    )


def test_llm_intent_classifier_parses_structured_response() -> None:
    classifier, model = _build_classifier(
        '{"matched_skills":["dog_profile:recall"],"intent":"known","confidence":0.84,"reasoning":"The user asks for a stored dog fact."}'
    )

    result = classifier.classify(_build_context())

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:recall",)
    assert result.confidence == 0.84
    assert result.reasoning == "The user asks for a stored dog fact."
    assert "routing classifier" in model.prompts[0]
    assert model.request_options == [{"timeout": 15}]
    metrics_payload = render_prometheus_metrics()
    assert 'tailmate_llm_latency_seconds_count{model="gemini-test"} 1' in metrics_payload


def test_llm_intent_classifier_filters_unknown_skill_ids() -> None:
    classifier, _ = _build_classifier(
        '{"matched_skills":["unknown","knowledge_base"],"intent":"open","confidence":0.62,"reasoning":"General question."}'
    )

    result = classifier.classify(_build_context("How often should I feed a puppy?"))

    assert result.intent == "open"
    assert result.matched_skills == ("knowledge_base",)


def test_llm_intent_classifier_strips_markdown_fences() -> None:
    classifier, _ = _build_classifier(
        '```json\n{"matched_skills":["dog_profile:recall"],"intent":"known","confidence":0.84,"reasoning":"The user asks for a stored dog fact."}\n```'
    )

    result = classifier.classify(_build_context())

    assert result.matched_skills == ("dog_profile:recall",)


def test_llm_intent_classifier_deduplicates_skill_ids() -> None:
    classifier, _ = _build_classifier(
        '{"matched_skills":["dog_profile:enrich","dog_profile:enrich","knowledge_base"],"intent":"open","confidence":0.72,"reasoning":"Combined routing."}'
    )

    result = classifier.classify(_build_context("Buddy has a cough, should I worry?"))

    assert result.matched_skills == ("dog_profile:enrich", "knowledge_base")


def test_llm_intent_classifier_rewrites_known_without_executable_skills_to_open() -> None:
    classifier, _ = _build_classifier(
        '{"matched_skills":["not-real-skill"],"intent":"known","confidence":0.91,"reasoning":"Model guessed a missing skill."}'
    )

    result = classifier.classify(_build_context())

    assert result.intent == "open"
    assert result.matched_skills == ("knowledge_base",)


def test_llm_intent_classifier_excludes_strip_metadata_from_prompt() -> None:
    classifier, model = _build_classifier(
        '{"matched_skills":["knowledge_base"],"intent":"open","confidence":0.62,"reasoning":"General question."}'
    )

    classifier.classify(_build_context("How often should I feed a puppy?"))

    assert "strip_metadata" not in model.prompts[0]


def test_llm_intent_classifier_prompt_includes_enrich_bias_for_dog_statements() -> None:
    classifier, model = _build_classifier(
        '{"matched_skills":["knowledge_base"],"intent":"open","confidence":0.62,"reasoning":"General question."}'
    )

    classifier.classify(_build_context("我狗狗爱吃青菜"))

    assert "declarative statements about the active dog" in model.prompts[0]
    assert "explicitly asks to save, record, or remember" in model.prompts[0]


def test_llm_intent_classifier_rejects_invalid_payload() -> None:
    classifier, _ = _build_classifier('{"matched_skills":"oops","intent":"known"}')

    with pytest.raises(AdapterError, match="invalid matched_skills"):
        classifier.classify(_build_context())
