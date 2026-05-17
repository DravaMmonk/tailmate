from __future__ import annotations

from tailmate.contracts.dog_profile import DogProfile
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.models.skill_spec import SkillSpec
from tailmate.agent_runtime.pipeline.skills import register_standard_runtime_skills
from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.rule_based_intent_classifier import RuleBasedIntentClassifier
from tailmate.skills.base import Skill
from tailmate.skills.registry import InMemorySkillRegistry


class FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeDogProfileAdapter:
    def __init__(self) -> None:
        self.profiles = {
            "dog-1": DogProfile(dog_id="dog-1", user_id="user-1", name="Buddy"),
            "dog-2": DogProfile(dog_id="dog-2", user_id="user-1", name="Peanut"),
        }

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None:
        profile = self.profiles.get(dog_id)
        if profile is None:
            return None
        return profile.model_copy(update={"user_id": requesting_user_id})

    def list_profiles(self, *, requesting_user_id: str) -> list[DogProfile]:
        return [
            profile.model_copy(update={"user_id": requesting_user_id})
            for profile in self.profiles.values()
            if profile.user_id == "user-1"
        ]


def _build_registry(*tool_ids: str) -> InMemorySkillRegistry:
    registry = InMemorySkillRegistry()
    registry.register(
        Skill(
            spec=SkillSpec(
                skill_id="test-skill",
                description="test",
                tool_ids=list(tool_ids),
            ),
            tools=[FakeTool(tool_id) for tool_id in tool_ids],
        )
    )
    register_standard_runtime_skills(registry)
    return registry


def _build_context(
    *,
    message: str,
    session_attributes: dict[str, object] | None = None,
    request_metadata: dict[str, object] | None = None,
    strip_request: dict[str, object] | None = None,
    turns: list[dict[str, object]] | None = None,
) -> TurnContext:
    return TurnContext(
        session=SessionContext(
            session_id="session-1",
            turns=turns or [],
            attributes=session_attributes or {},
        ),
        session_id="session-1",
        message=message,
        locale="en-AU",
        locale_resolution=None,
        request_metadata=request_metadata or {},
        strip_request=strip_request,
    )


def test_rule_based_intent_classifier_matches_strip_metadata_request() -> None:
    classifier = RuleBasedIntentClassifier(_build_registry("strip_metadata.upload"))
    ctx = _build_context(
        message="hello",
        strip_request={"dog_id": "dog-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("strip_metadata",)
    assert result.confidence == 1.0


def test_rule_based_intent_classifier_short_circuits_strip_metadata_over_profile_routes() -> None:
    classifier = RuleBasedIntentClassifier(
        _build_registry("strip_metadata.upload", "dog_profile.create")
    )
    ctx = _build_context(
        message="My dog is Peanut",
        request_metadata={"user_id": "user-1"},
        strip_request={"dog_id": "dog-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("strip_metadata",)


def test_rule_based_intent_classifier_matches_dog_profile_create() -> None:
    classifier = RuleBasedIntentClassifier(_build_registry("dog_profile.create"))
    ctx = _build_context(
        message="My dog is Peanut",
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:create",)


def test_rule_based_intent_classifier_matches_dog_profile_enrich() -> None:
    classifier = RuleBasedIntentClassifier(_build_registry("dog_profile.enrich"))
    ctx = _build_context(
        message="Buddy is 4 years old and weighs 15 kg.",
        session_attributes={"dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:enrich",)


def test_rule_based_intent_classifier_keeps_enrich_and_knowledge_base_for_active_dog_question() -> None:
    classifier = RuleBasedIntentClassifier(_build_registry("dog_profile.enrich"))
    ctx = _build_context(
        message="Buddy has been coughing. Should I be worried?",
        session_attributes={"dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:enrich", "knowledge_base")


def test_rule_based_intent_classifier_matches_dog_profile_recall() -> None:
    classifier = RuleBasedIntentClassifier(_build_registry("dog_profile.enrich"))
    ctx = _build_context(
        message="What is my dog's name?",
        session_attributes={"dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:recall",)


def test_rule_based_intent_classifier_matches_name_based_recall_for_active_dog() -> None:
    registry = _build_registry("dog_profile.enrich")
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
    )
    classifier = RuleBasedIntentClassifier(registry)
    ctx = _build_context(
        message="What breed is Buddy?",
        session_attributes={"dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:recall",)


def test_rule_based_intent_classifier_routes_chinese_age_question_to_recall() -> None:
    registry = _build_registry("dog_profile.enrich")
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
    )
    classifier = RuleBasedIntentClassifier(registry)
    ctx = _build_context(
        message="我的狗多少岁",
        session_attributes={"dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
        turns=[
            {"role": "user", "message": "我的狗叫豆豆"},
            {"role": "assistant", "message": "Created a profile for 豆豆!"},
        ],
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:recall",)


def test_rule_based_intent_classifier_routes_chinese_info_question_to_recall() -> None:
    registry = _build_registry("dog_profile.enrich")
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
    )
    classifier = RuleBasedIntentClassifier(registry)
    ctx = _build_context(
        message="你知道关于Buddy的哪些信息",
        session_attributes={"dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:recall",)


def test_rule_based_intent_classifier_uses_recent_history_when_active_dog_name_is_not_loaded() -> None:
    classifier = RuleBasedIntentClassifier(_build_registry("dog_profile.enrich"))
    ctx = _build_context(
        message="What breed is Buddy?",
        session_attributes={"dog_id": "dog-1"},
        request_metadata={"user_id": ""},
        turns=[
            {"role": "user", "message": "My dog is Buddy."},
            {"role": "assistant", "message": "Created a profile for Buddy!"},
            {"role": "user", "message": "What breed is Buddy?"},
        ],
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:recall",)


def test_rule_based_intent_classifier_defaults_to_open_question_with_knowledge_base() -> None:
    classifier = RuleBasedIntentClassifier(_build_registry())
    ctx = _build_context(message="How often should I feed my dog?")

    result = classifier.classify(ctx)

    assert result.intent == "open"
    assert result.matched_skills == ("knowledge_base",)
    assert result.confidence == 0.0


def test_rule_based_intent_classifier_matches_explicit_active_dog_switch() -> None:
    registry = _build_registry("dog_profile.enrich")
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
    )
    classifier = RuleBasedIntentClassifier(registry)
    ctx = _build_context(
        message="Switch to Peanut",
        session_attributes={"active_dog_id": "dog-1", "dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:switch",)


def test_rule_based_intent_classifier_prompts_for_multi_dog_disambiguation() -> None:
    registry = _build_registry("dog_profile.enrich")
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
    )
    classifier = RuleBasedIntentClassifier(registry)
    ctx = _build_context(
        message="What is my dog's name?",
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:switch",)


def test_rule_based_intent_classifier_keeps_switch_and_recall_for_named_other_dog() -> None:
    registry = _build_registry("dog_profile.enrich")
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
    )
    classifier = RuleBasedIntentClassifier(registry)
    ctx = _build_context(
        message="What breed is Peanut?",
        session_attributes={"active_dog_id": "dog-1", "dog_id": "dog-1"},
        request_metadata={"user_id": "user-1"},
    )

    result = classifier.classify(ctx)

    assert result.intent == "known"
    assert result.matched_skills == ("dog_profile:switch", "dog_profile:recall")
