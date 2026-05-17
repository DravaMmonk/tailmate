from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from tailmate.adapters.dog_profile.extractors import (
    BreedMatcher,
    CompositeExtractor,
    detect_dog_name,
    GeminiStructuredExtractorClient,
    LLMFlashExtractor,
    RuleBasedExtractor,
)
from tailmate.contracts.dog_profile import DogProfile, ExtractionResult
from tailmate.contracts.errors import AdapterError


class FakeVertexAIInitializer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs) -> None:
        self.calls.append(kwargs)


class FakeGenerationResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeGenerativeModel:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    def generate_content(self, contents, *, generation_config=None, **kwargs):
        self.calls.append(
            {
                "contents": contents,
                "generation_config": generation_config,
                "kwargs": kwargs,
            }
        )
        return FakeGenerationResponse(self.response_text)


class RecordingFlashExtractor:
    strategy_name = "flash"

    def __init__(self, result: ExtractionResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def extract_with_hints(
        self,
        *,
        user_message: str,
        current_profile: DogProfile,
        rule_hints: dict[str, object] | None,
        rule_raw_note: str | None,
    ) -> ExtractionResult:
        self.calls.append(
            {
                "user_message": user_message,
                "current_profile": current_profile,
                "rule_hints": rule_hints,
                "rule_raw_note": rule_raw_note,
            }
        )
        return self.result


def test_breed_matcher_matches_multilingual_aliases_and_reports_coverage() -> None:
    matcher = BreedMatcher()

    assert matcher.match("Our chihuaha is tiny.") == "Chihuahua"
    assert matcher.match("我家狗是法斗") == "French Bulldog"
    assert matcher.match("我隻狗係法鬥") == "French Bulldog"

    coverage = matcher.coverage_report()
    assert coverage["en"] > 0
    assert coverage["zh-Hans"] > 0
    assert coverage["yue"] > 0


def test_detect_dog_name_supports_my_dog_name_is_english_phrase() -> None:
    assert detect_dog_name("My dog Mochi is a desexed female French Bulldog.") == "Mochi"


def test_detect_dog_name_strips_possessive_prefix_for_zh_hans_name_intro() -> None:
    assert (
        detect_dog_name("我的豆豆是一只男性4岁 法式斗牛犬，它很活泼，体重4千克")
        == "豆豆"
    )


def test_detect_dog_name_does_not_extract_non_dog_possessive_intro() -> None:
    assert detect_dog_name("我的工作是工程师。") is None


def test_detect_dog_name_keeps_short_dog_specific_possessive_intro() -> None:
    assert detect_dog_name("我的豆豆是公狗。") == "豆豆"


def test_rule_based_extractor_extracts_structured_lookup_fields() -> None:
    extractor = RuleBasedExtractor()

    result = extractor.extract(
        "DouDou is a frenchie boy, desexed, 3 years old and 26 lb",
        DogProfile(name="DouDou"),
    )

    assert result.structured_fields == {
        "breed": "French Bulldog",
        "age_months": 36,
        "weight_kg": 11.79,
        "sex": "male",
        "neutered": True,
    }
    assert result.confidence == 0.92
    assert result.strategy_used == "rule"


def test_rule_based_extractor_extracts_half_months_from_chinese_age_expression() -> None:
    extractor = RuleBasedExtractor()

    result = extractor.extract(
        "我家狗叫豆豆，法斗，母狗，已绝育，两个半月，4公斤",
        DogProfile(name="豆豆"),
    )

    assert result.structured_fields["breed"] == "French Bulldog"
    assert result.structured_fields["age_months"] == 3
    assert result.structured_fields["weight_kg"] == 4.0
    assert result.structured_fields["sex"] == "female"
    assert result.structured_fields["neutered"] is True


def test_rule_based_extractor_supports_single_character_chinese_sex_tokens() -> None:
    extractor = RuleBasedExtractor()

    result = extractor.extract(
        "我家狗是公，没绝育。",
        DogProfile(name="豆豆"),
    )

    assert result.structured_fields["sex"] == "male"
    assert result.structured_fields["neutered"] is False


def test_rule_based_extractor_extracts_birthdate_based_age() -> None:
    extractor = RuleBasedExtractor(now_provider=lambda: datetime(2026, 3, 27, tzinfo=timezone.utc))

    result = extractor.extract(
        "Bean was born on 2024-09-27.",
        DogProfile(name="Bean"),
    )

    assert result.structured_fields["age_months"] == 18


def test_rule_based_extractor_maps_temperament_activity_and_diet_to_standard_labels() -> None:
    extractor = RuleBasedExtractor()

    result = extractor.extract(
        "My dog is clingy, very active, and on a raw diet.",
        DogProfile(name="Bean"),
    )

    assert result.structured_fields == {
        "temperament": "affectionate",
        "activity_level": "high",
        "diet": "raw",
    }


def test_rule_based_extractor_supports_cantonese_keyword_groups() -> None:
    extractor = RuleBasedExtractor()

    result = extractor.extract(
        "我隻狗好痴身，唔愛郁，而家食狗糧。",
        DogProfile(name="Bean"),
    )

    assert result.structured_fields == {
        "temperament": "affectionate",
        "activity_level": "low",
        "diet": "dry",
    }


def test_rule_based_extractor_extracts_medical_fields_and_flags_escalation() -> None:
    extractor = RuleBasedExtractor()

    assessment = extractor.analyze(
        "豆豆对鸡肉过敏，正在用Apoquel，之前膝盖做过手术",
        DogProfile(name="豆豆"),
    )

    assert assessment.result.structured_fields == {
        "medical_history": ["之前膝盖做过手术"],
        "allergies": ["鸡肉"],
        "current_medications": ["Apoquel"],
    }
    assert assessment.result.confidence == 0.72
    assert assessment.should_escalate is True
    assert assessment.medical_triggered is True


def test_rule_based_extractor_uses_whole_message_raw_note_for_dog_context() -> None:
    extractor = RuleBasedExtractor()

    assessment = extractor.analyze(
        "My dog follows me everywhere, waits by the door, and stares at me until dinner time.",
        DogProfile(name="Bean"),
    )

    assert assessment.result.structured_fields == {}
    assert (
        assessment.result.raw_note
        == "My dog follows me everywhere, waits by the door, and stares at me until dinner time."
    )
    assert assessment.result.confidence == 0.45
    assert assessment.should_escalate is True
    assert assessment.raw_note_fallback_used is True


def test_rule_based_extractor_uses_whole_message_raw_note_for_short_behavior_note() -> None:
    extractor = RuleBasedExtractor()

    assessment = extractor.analyze(
        "豆豆特别怕吸尘器，每天遛两次。",
        DogProfile(name="豆豆"),
    )

    assert assessment.result.structured_fields == {}
    assert assessment.result.raw_note == "豆豆特别怕吸尘器，每天遛两次。"
    assert assessment.should_escalate is True
    assert assessment.raw_note_fallback_used is True


def test_rule_based_extractor_does_not_mix_structured_fields_with_raw_note_fallback() -> None:
    extractor = RuleBasedExtractor()

    assessment = extractor.analyze(
        "Bean is a couch potato.",
        DogProfile(name="Bean"),
    )

    assert assessment.result.structured_fields == {"activity_level": "low"}
    assert assessment.result.raw_note is None
    assert assessment.should_escalate is False
    assert assessment.raw_note_fallback_used is False


def test_flash_extractor_includes_rule_hints_in_prompt() -> None:
    initializer = FakeVertexAIInitializer()
    model = FakeGenerativeModel(
        '{"structured_fields": {"weight_kg": 12.5}, "raw_note": null, "confidence": 0.76}'
    )
    extractor = LLMFlashExtractor(
        client=GeminiStructuredExtractorClient(
            model_name="gemini-test",
            project_id="test-project",
            location="us-central1",
            api_key="test-key",
            initializer=initializer,
            model_factory=lambda model_name: model,
        )
    )

    result = extractor.extract_with_hints(
        user_message="He weighs 12.5 kg now.",
        current_profile=DogProfile(name="DouDou"),
        rule_hints={"weight_kg": 12.0},
        rule_raw_note="Current weight may have changed.",
    )

    assert result.structured_fields == {"weight_kg": 12.5}
    assert result.confidence == 0.76
    assert result.strategy_used == "flash"
    assert initializer.calls[0]["project"] == "test-project"
    assert initializer.calls[0]["location"] == "us-central1"
    assert initializer.calls[0]["api_key"] == "test-key"
    prompt = model.calls[0]["contents"]
    assert '"weight_kg": 12.0' in prompt
    assert "Current weight may have changed." in prompt
    config_payload = model.calls[0]["generation_config"].to_dict()
    assert config_payload["response_mime_type"] == "application/json"
    assert config_payload["temperature"] == 0.0


def test_flash_extractor_retries_transient_model_failures_before_succeeding(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "tailmate.adapters.dog_profile.extractors.tenacity.sleep",
        lambda _seconds: None,
    )
    attempts = {"count": 0}
    initializer = FakeVertexAIInitializer()

    class FlakyModel:
        def __init__(self, _response_text: str) -> None:
            self.calls: list[dict[str, object]] = []

        def generate_content(self, contents, *, generation_config=None, **kwargs):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("transient gemini failure")
            self.calls.append(
                {
                    "contents": contents,
                    "generation_config": generation_config,
                    "kwargs": kwargs,
                }
            )
            return FakeGenerationResponse(
                '{"structured_fields": {"weight_kg": 12.5}, "raw_note": null, "confidence": 0.76}'
            )

    extractor = LLMFlashExtractor(
        client=GeminiStructuredExtractorClient(
            model_name="gemini-test",
            project_id="test-project",
            location="us-central1",
            api_key="test-key",
            initializer=initializer,
            model_factory=lambda model_name: FlakyModel(model_name),
        )
    )

    result = extractor.extract_with_hints(
        user_message="He weighs 12.5 kg now.",
        current_profile=DogProfile(name="DouDou"),
        rule_hints={"weight_kg": 12.0},
        rule_raw_note="Current weight may have changed.",
    )

    assert result.structured_fields == {"weight_kg": 12.5}
    assert attempts["count"] == 3
    assert len(initializer.calls) == 3


def test_flash_extractor_logs_and_raises_after_retry_exhaustion(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        "tailmate.adapters.dog_profile.extractors.tenacity.sleep",
        lambda _seconds: None,
    )
    attempts = {"count": 0}
    initializer = FakeVertexAIInitializer()

    class FlakyModel:
        def __init__(self, _response_text: str) -> None:
            return None

        def generate_content(self, contents, *, generation_config=None, **kwargs):
            del contents, generation_config, kwargs
            attempts["count"] += 1
            raise RuntimeError("persistent gemini failure")

    extractor = LLMFlashExtractor(
        client=GeminiStructuredExtractorClient(
            model_name="gemini-test",
            project_id="test-project",
            location="us-central1",
            api_key="test-key",
            initializer=initializer,
            model_factory=lambda model_name: FlakyModel(model_name),
        )
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(AdapterError, match="Failed to reach Gemini model"):
            extractor.extract_with_hints(
                user_message="He weighs 12.5 kg now.",
                current_profile=DogProfile(name="DouDou"),
                rule_hints={"weight_kg": 12.0},
                rule_raw_note="Current weight may have changed.",
            )

    assert attempts["count"] == 3
    assert len(initializer.calls) == 3
    record = next(
        entry
        for entry in caplog.records
        if entry.getMessage() == "dog_profile.gemini_request_failed_after_retries"
    )
    assert record.model_name == "gemini-test"
    assert record.attempts == 3
    assert record.error_type == "RuntimeError"


def test_composite_extractor_escalates_on_medical_rules_and_merges_flash_output() -> None:
    flash_extractor = RecordingFlashExtractor(
        ExtractionResult(
            structured_fields={"allergies": ["chicken protein"]},
            raw_note=None,
            confidence=0.81,
            strategy_used="flash",
        )
    )
    extractor = CompositeExtractor(
        rule_extractor=RuleBasedExtractor(),
        flash_extractor=flash_extractor,
    )

    result = extractor.extract(
        "Bean is a frenchie and allergic to chicken.",
        DogProfile(name="Bean"),
    )

    assert result.structured_fields == {
        "breed": "French Bulldog",
        "allergies": ["chicken protein"],
    }
    assert result.strategy_used == "flash"
    assert flash_extractor.calls[0]["rule_hints"] == {
        "breed": "French Bulldog",
        "allergies": ["chicken"],
    }
