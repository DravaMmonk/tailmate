from __future__ import annotations

from datetime import datetime, timezone

from tailmate.adapters.dog_profile.db_adapter import apply_extraction_result
from tailmate.adapters.dog_profile.extractors import RuleBasedExtractor
from tailmate.agent_runtime.current_context import (
    RuntimeRequestContext,
    reset_current_context,
    set_current_context,
)
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.services.graph_orchestrator import GraphOrchestrator
from tailmate.agent_runtime.services.rule_based_intent_classifier import RuleBasedIntentClassifier
from tailmate.contracts.constants import DOG_PROFILE_RESULT_METADATA_KEY
from tailmate.contracts.constants import KNOWLEDGE_BASE_RESULT_METADATA_KEY, TURN_DEBUG_METADATA_KEY
from tailmate.contracts.dog_profile import (
    CreateDogProfileOutput,
    DogProfile,
    EnrichDogProfileOutput,
)
from tailmate.contracts.errors import AuthorizationError
from tailmate.skills.dog_profile.skill import build_dog_profile_skill
from tailmate.skills.registry import InMemorySkillRegistry


class FakeSessionStore:
    def __init__(self) -> None:
        self.contexts: dict[str, SessionContext] = {}

    def load(self, session_id: str) -> SessionContext:
        return self.contexts.get(session_id, SessionContext(session_id=session_id))

    def save(self, context: SessionContext) -> None:
        self.contexts[context.session_id] = context


class FakeObservability:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event_name: str, **kwargs: object) -> None:
        self.events.append((event_name, kwargs))

    def error(self, event_name: str, **kwargs: object) -> None:
        self.events.append((event_name, kwargs))


class InMemoryDogProfileDBAdapter:
    def __init__(self) -> None:
        self.profiles: dict[str, DogProfile] = {}
        self.counter = 0

    def create_profile(self, request) -> CreateDogProfileOutput:
        self.counter += 1
        dog_id = f"dog-{self.counter}"
        now = datetime.now(timezone.utc)
        self.profiles[dog_id] = DogProfile(
            dog_id=dog_id,
            user_id=request.user_id,
            name=request.name,
            created_at=now,
            updated_at=now,
        )
        return CreateDogProfileOutput(
            dog_id=dog_id,
            profile_summary=request.name,
            created_at=now,
        )

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None:
        profile = self.profiles.get(dog_id)
        if profile is None:
            return None
        if profile.user_id != requesting_user_id:
            raise AuthorizationError(f"Dog profile '{dog_id}' is not owned by the requesting user.")
        return profile

    def list_profiles(self, *, requesting_user_id: str) -> list[DogProfile]:
        return [
            profile
            for profile in self.profiles.values()
            if profile.user_id == requesting_user_id
        ]

    def enrich_profile(self, request, extraction_result) -> EnrichDogProfileOutput:
        current_profile = self.profiles[request.dog_id]
        mutation = apply_extraction_result(current_profile, extraction_result)
        self.profiles[request.dog_id] = mutation.updated_profile
        return EnrichDogProfileOutput(
            updated_fields=mutation.updated_fields,
            raw_note=mutation.stored_raw_note,
            extraction_strategy_used=extraction_result.strategy_used,
        )


def test_graph_orchestrator_creates_and_enriches_dog_profile_from_conversation() -> None:
    session_store = FakeSessionStore()
    observability = FakeObservability()
    dog_profile_db_adapter = InMemoryDogProfileDBAdapter()
    registry = InMemorySkillRegistry()
    registry.register(
        build_dog_profile_skill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            profile_extractor=RuleBasedExtractor(),
        )
    )
    orchestrator = GraphOrchestrator(
        session_store=session_store,
        skill_registry=registry,
        observability=observability,
        intent_classifier=RuleBasedIntentClassifier(registry),
    )

    first_token = set_current_context(
        RuntimeRequestContext(
            session_id="session-1",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        first_context = orchestrator.run("session-1", "我家狗叫豆豆")
    finally:
        reset_current_context(first_token)

    dog_id = first_context.attributes["dog_id"]
    assert first_context.attributes["last_response"].startswith("已为豆豆建立档案")
    assert first_context.attributes[DOG_PROFILE_RESULT_METADATA_KEY]["action"] == "create"
    assert first_context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "skill:dog_profile:create"
    assert dog_profile_db_adapter.profiles[dog_id].name == "豆豆"

    second_token = set_current_context(
        RuntimeRequestContext(
            session_id="session-1",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        second_context = orchestrator.run(
            "session-1",
            "豆豆是柯基，三岁，15公斤，之前膝盖做过手术",
        )
    finally:
        reset_current_context(second_token)

    updated_profile = dog_profile_db_adapter.profiles[dog_id]
    assert updated_profile.user_id == "user-1"
    assert updated_profile.breed == "Corgi"
    assert updated_profile.age_months == 36
    assert updated_profile.weight_kg == 15.0
    assert updated_profile.medical_history == ["之前膝盖做过手术"]
    assert second_context.attributes["last_response"].startswith("已更新狗狗档案：")
    assert second_context.attributes[DOG_PROFILE_RESULT_METADATA_KEY]["action"] == "enrich"
    assert second_context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "skill:dog_profile:enrich"
    assert observability.events[0][0] == "orchestrator_dog_profile_create"
    assert any(event_name == "orchestrator_dog_profile_enrich" for event_name, _ in observability.events)


def test_graph_orchestrator_recalls_stored_dog_profile_before_fallback() -> None:
    session_store = FakeSessionStore()
    observability = FakeObservability()
    dog_profile_db_adapter = InMemoryDogProfileDBAdapter()
    registry = InMemorySkillRegistry()
    registry.register(
        build_dog_profile_skill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            profile_extractor=RuleBasedExtractor(),
        )
    )
    orchestrator = GraphOrchestrator(
        session_store=session_store,
        skill_registry=registry,
        observability=observability,
        intent_classifier=RuleBasedIntentClassifier(registry),
        dog_profile_db_adapter=dog_profile_db_adapter,
    )

    create_token = set_current_context(
        RuntimeRequestContext(
            session_id="session-recall",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        created_context = orchestrator.run("session-recall", "我家狗叫豆豆")
    finally:
        reset_current_context(create_token)

    dog_id = created_context.attributes["dog_id"]

    enrich_token = set_current_context(
        RuntimeRequestContext(
            session_id="session-recall",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        orchestrator.run("session-recall", "豆豆三岁，15公斤")
    finally:
        reset_current_context(enrich_token)

    recall_token = set_current_context(
        RuntimeRequestContext(
            session_id="session-recall",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        recalled_context = orchestrator.run("session-recall", "我的狗叫什么？")
    finally:
        reset_current_context(recall_token)

    assert recalled_context.attributes["dog_id"] == dog_id
    assert recalled_context.attributes["last_response"].startswith("我目前知道豆豆的资料：")
    assert "年龄: 3岁" in recalled_context.attributes["last_response"]
    assert "体重: 15 kg" in recalled_context.attributes["last_response"]
    assert recalled_context.attributes[DOG_PROFILE_RESULT_METADATA_KEY]["action"] == "recall"
    assert recalled_context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "memory:dog_profile"
    assert any(event_name == "orchestrator_dog_profile_recall" for event_name, _ in observability.events)


def test_graph_orchestrator_enriches_and_answers_question_in_same_turn() -> None:
    class FakeKnowledgeRetriever:
        def __init__(self) -> None:
            self.requests: list[tuple[str, str, str | None]] = []

        def query(self, request) -> EnrichDogProfileOutput:
            self.requests.append((request.user_message, request.locale, request.dog_context))
            return type(
                "KnowledgeResult",
                (),
                {
                    "status": "hit",
                    "answer": "Because Buddy recently had a cough, monitor him closely and see a vet if it returns.",
                    "confidence": 0.92,
                    "sources": ["Tailmate Respiratory Guide"],
                    "model_dump": lambda self, mode="json": {
                        "status": "hit",
                        "answer": "Because Buddy recently had a cough, monitor him closely and see a vet if it returns.",
                        "confidence": 0.92,
                        "sources": ["Tailmate Respiratory Guide"],
                    },
                },
            )()

    session_store = FakeSessionStore()
    observability = FakeObservability()
    dog_profile_db_adapter = InMemoryDogProfileDBAdapter()
    registry = InMemorySkillRegistry()
    registry.register(
        build_dog_profile_skill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            profile_extractor=RuleBasedExtractor(),
        )
    )
    knowledge_retriever = FakeKnowledgeRetriever()
    orchestrator = GraphOrchestrator(
        session_store=session_store,
        skill_registry=registry,
        observability=observability,
        intent_classifier=RuleBasedIntentClassifier(registry),
        dog_profile_db_adapter=dog_profile_db_adapter,
        knowledge_retriever=knowledge_retriever,
    )

    create_token = set_current_context(
        RuntimeRequestContext(
            session_id="session-enrich-answer",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        orchestrator.run("session-enrich-answer", "My dog is Buddy")
    finally:
        reset_current_context(create_token)

    turn_token = set_current_context(
        RuntimeRequestContext(
            session_id="session-enrich-answer",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        context = orchestrator.run(
            "session-enrich-answer",
            "He had a cough last week, should I be worried?",
        )
    finally:
        reset_current_context(turn_token)

    assert context.attributes["last_response"].startswith("Updated your dog's profile:")
    assert "Because Buddy recently had a cough" in context.attributes["last_response"]
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "skill:dog_profile:enrich+knowledge_base"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "dog_profile.enrich_and_answer"
    assert context.attributes[KNOWLEDGE_BASE_RESULT_METADATA_KEY]["status"] == "hit"


def test_graph_orchestrator_switches_active_dog_for_named_recall_queries() -> None:
    session_store = FakeSessionStore()
    observability = FakeObservability()
    dog_profile_db_adapter = InMemoryDogProfileDBAdapter()
    dog_profile_db_adapter.profiles = {
        "dog-1": DogProfile(dog_id="dog-1", user_id="user-1", name="Buddy", breed="Corgi"),
        "dog-2": DogProfile(dog_id="dog-2", user_id="user-1", name="Peanut", breed="Beagle"),
    }
    registry = InMemorySkillRegistry()
    registry.register(
        build_dog_profile_skill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            profile_extractor=RuleBasedExtractor(),
        )
    )
    orchestrator = GraphOrchestrator(
        session_store=session_store,
        skill_registry=registry,
        observability=observability,
        intent_classifier=RuleBasedIntentClassifier(registry),
        dog_profile_db_adapter=dog_profile_db_adapter,
    )
    session_store.contexts["session-switch"] = SessionContext(
        session_id="session-switch",
        attributes={"active_dog_id": "dog-1", "dog_id": "dog-1"},
    )

    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-switch",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        context = orchestrator.run("session-switch", "What breed is Peanut?")
    finally:
        reset_current_context(token)

    assert context.attributes["active_dog_id"] == "dog-2"
    assert context.attributes["dog_id"] == "dog-2"
    assert "Peanut" in context.attributes["last_response"]
    assert "Beagle" in context.attributes["last_response"]
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "memory:dog_profile"


def test_graph_orchestrator_prompts_for_dog_selection_when_multiple_profiles_exist() -> None:
    session_store = FakeSessionStore()
    observability = FakeObservability()
    dog_profile_db_adapter = InMemoryDogProfileDBAdapter()
    dog_profile_db_adapter.profiles = {
        "dog-1": DogProfile(dog_id="dog-1", user_id="user-1", name="Buddy"),
        "dog-2": DogProfile(dog_id="dog-2", user_id="user-1", name="Peanut"),
    }
    registry = InMemorySkillRegistry()
    registry.register(
        build_dog_profile_skill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            profile_extractor=RuleBasedExtractor(),
        )
    )
    orchestrator = GraphOrchestrator(
        session_store=session_store,
        skill_registry=registry,
        observability=observability,
        intent_classifier=RuleBasedIntentClassifier(registry),
        dog_profile_db_adapter=dog_profile_db_adapter,
    )

    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-multi",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        context = orchestrator.run("session-multi", "What is my dog's name?")
    finally:
        reset_current_context(token)

    assert "Buddy" in context.attributes["last_response"]
    assert "Peanut" in context.attributes["last_response"]
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "memory:dog_profile_selection"
    assert "active_dog_id" not in context.attributes


def test_graph_orchestrator_preserves_response_when_session_save_fails() -> None:
    """The computed response must survive a session-save failure so users
    are not shown a generic error when the database is temporarily unreachable."""

    class FailingSaveSessionStore:
        def __init__(self) -> None:
            self.contexts: dict[str, SessionContext] = {}

        def load(self, session_id: str) -> SessionContext:
            return self.contexts.get(session_id, SessionContext(session_id=session_id))

        def save(self, context: SessionContext) -> None:
            raise ConnectionError("simulated session save failure")

    session_store = FailingSaveSessionStore()
    observability = FakeObservability()
    dog_profile_db_adapter = InMemoryDogProfileDBAdapter()
    registry = InMemorySkillRegistry()
    registry.register(
        build_dog_profile_skill(
            dog_profile_db_adapter=dog_profile_db_adapter,
            profile_extractor=RuleBasedExtractor(),
        )
    )
    orchestrator = GraphOrchestrator(
        session_store=session_store,
        skill_registry=registry,
        observability=observability,
        intent_classifier=RuleBasedIntentClassifier(registry),
    )

    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-save-fail",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )
    try:
        context = orchestrator.run("session-save-fail", "我家狗叫豆豆")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith("已为豆豆建立档案")
    save_errors = [
        (name, kwargs)
        for name, kwargs in observability.events
        if name == "orchestrator_session_save_failed"
    ]
    assert len(save_errors) == 1
    assert save_errors[0][1]["error_type"] == "ConnectionError"
