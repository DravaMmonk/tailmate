from __future__ import annotations

from tailmate.agent_runtime.current_context import (
    RuntimeRequestContext,
    reset_current_context,
    set_current_context,
)
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.models.skill_spec import SkillSpec
from tailmate.agent_runtime.services.graph_orchestrator import GraphOrchestrator
from tailmate.agent_runtime.services.rule_based_intent_classifier import RuleBasedIntentClassifier
from tailmate.adapters.vertex_agent_engine.observability import CloudObservability
from tailmate.contracts.constants import (
    DOG_PROFILE_CREATE_TOOL_ID,
    KNOWLEDGE_BASE_RESULT_METADATA_KEY,
    TURN_DEBUG_METADATA_KEY,
)
from tailmate.contracts.dog_profile import DogProfile
from tailmate.contracts.errors import AuthorizationError, DomainError
from tailmate.contracts.knowledge import KnowledgeQueryOutput
from tailmate.metrics import render_prometheus_metrics, reset_metrics_registry
from tailmate.skills.base import Skill
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


class ExplodingCreateTool:
    name = DOG_PROFILE_CREATE_TOOL_ID

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        raise DomainError(f"Dog profile create failed for {payload['name']}.")


class FakeKnowledgeRetriever:
    def __init__(
        self,
        result: KnowledgeQueryOutput | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result or KnowledgeQueryOutput(status="miss")
        self.error = error
        self.requests: list[tuple[str, str, str | None]] = []

    def query(self, request) -> KnowledgeQueryOutput:
        self.requests.append((request.user_message, request.locale, request.dog_context))
        if self.error is not None:
            raise self.error
        return self.result


class FakeConversationalResponder:
    def __init__(
        self,
        *,
        text: str = "General dog-health guidance.",
        provenance: str = "llm_generated",
        error: Exception | None = None,
    ) -> None:
        self.text = text
        self.provenance = provenance
        self.error = error
        self.requests: list[object] = []

    def generate(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return type(
            "ConversationalResponse",
            (),
            {
                "text": self.text,
                "provenance": self.provenance,
                "model": "gemini-test",
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )()


class StreamingConversationalResponder(FakeConversationalResponder):
    def __init__(self, *, chunks: tuple[str, ...]) -> None:
        super().__init__(text="".join(chunks))
        self.chunks = chunks
        self.stream_requests: list[object] = []
        self.generate_calls = 0

    def generate(self, request):
        self.generate_calls += 1
        return super().generate(request)

    def stream_generate(self, request):
        self.stream_requests.append(request)
        yield from self.chunks


class EmptyEnrichTool:
    name = "dog_profile.enrich"

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        return {
            "updated_fields": {},
            "raw_note": None,
            "extraction_strategy_used": "rule",
        }


class ExplodingRecallAdapter:
    def load_profile(self, dog_id: str, *, requesting_user_id: str):
        raise AuthorizationError(f"Dog profile '{dog_id}' is not owned by the requesting user.")


class FakeDogProfileAdapter:
    def __init__(self, profiles: dict[str, DogProfile]) -> None:
        self.profiles = profiles

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None:
        profile = self.profiles.get(dog_id)
        if profile is None or profile.user_id != requesting_user_id:
            return None
        return profile


def build_orchestrator(
    *,
    session_store: FakeSessionStore | None = None,
    skill_registry: InMemorySkillRegistry | None = None,
    observability=None,
    dog_profile_db_adapter=None,
    knowledge_retriever=None,
    conversational_responder=None,
) -> GraphOrchestrator:
    registry = skill_registry or InMemorySkillRegistry()
    return GraphOrchestrator(
        session_store=session_store or FakeSessionStore(),
        skill_registry=registry,
        observability=observability or FakeObservability(),
        intent_classifier=RuleBasedIntentClassifier(registry),
        dog_profile_db_adapter=dog_profile_db_adapter,
        knowledge_retriever=knowledge_retriever,
        conversational_responder=conversational_responder,
    )


def test_graph_orchestrator_returns_localized_fallback_for_greeting_without_skill_match() -> None:
    reset_metrics_registry()
    orchestrator = build_orchestrator()
    token = set_current_context(RuntimeRequestContext(session_id="session-1", metadata={"channel": "web"}))

    try:
        context = orchestrator.run("session-1", "你好")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith("你好！")
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"] == "fallback.greeting"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["locale"] == "zh-Hans"
    assert context.turns[-1]["fallback_reason"] == "fallback.greeting"
    metrics_payload = render_prometheus_metrics()
    assert 'tailmate_sessions_total{channel="web"} 1' in metrics_payload


def test_graph_orchestrator_uses_returning_greeting_when_dog_name_is_in_recent_history() -> None:
    session_store = FakeSessionStore()
    session_store.contexts["session-returning-greeting"] = SessionContext(
        session_id="session-returning-greeting",
        turns=[
            {"role": "user", "message": "My dog Mochi is a desexed female French Bulldog."},
            {
                "role": "assistant",
                "message": "Created a profile for Mochi!",
                "source": "skill:dog_profile:create",
            },
        ],
    )
    orchestrator = build_orchestrator(session_store=session_store)
    token = set_current_context(RuntimeRequestContext(session_id="session-returning-greeting"))

    try:
        context = orchestrator.run("session-returning-greeting", "hello")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"] == "Welcome back! How can I help with Mochi today?"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"] == "fallback.greeting"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "fallback.greeting_returning"


def test_graph_orchestrator_short_circuits_new_empty_message_to_session_welcome() -> None:
    orchestrator = build_orchestrator()
    token = set_current_context(RuntimeRequestContext(session_id="session-welcome"))

    try:
        context = orchestrator.run("session-welcome", "")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith("Hi! I'm Tailmate's pet assistant.")
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "welcome"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "session.welcome"
    assert len(context.turns) == 1
    assert context.turns[0]["role"] == "assistant"
    assert context.turns[0]["response_key"] == "session.welcome"


def test_graph_orchestrator_uses_personalized_welcome_for_new_empty_message_with_known_dog() -> None:
    dog_profile_db_adapter = FakeDogProfileAdapter(
        {
            "dog-1": DogProfile(dog_id="dog-1", user_id="user-1", name="Buddy"),
        }
    )
    orchestrator = build_orchestrator(dog_profile_db_adapter=dog_profile_db_adapter)
    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-returning-welcome",
            metadata={"dog_id": "dog-1", "user_id": "user-1"},
            user_id="user-1",
        )
    )

    try:
        context = orchestrator.run("session-returning-welcome", "")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"] == "Welcome back! How can I help with Buddy today?"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "welcome"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "fallback.greeting_returning"


def test_graph_orchestrator_keeps_existing_session_empty_message_on_normal_pipeline() -> None:
    session_store = FakeSessionStore()
    session_store.contexts["session-existing-empty"] = SessionContext(
        session_id="session-existing-empty",
        turns=[{"role": "assistant", "message": "Earlier reply.", "source": "fallback"}],
    )
    orchestrator = build_orchestrator(session_store=session_store)
    token = set_current_context(RuntimeRequestContext(session_id="session-existing-empty"))

    try:
        context = orchestrator.run("session-existing-empty", "")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "fallback.no_skill_matched"
    assert context.turns[-2]["role"] == "user"
    assert context.turns[-2]["message"] == ""


def test_graph_orchestrator_audits_unsupported_locale_default_to_english() -> None:
    orchestrator = build_orchestrator()
    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-2",
            metadata={"locale": "fr-FR"},
        )
    )

    try:
        context = orchestrator.run("session-2", "bonjour")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith("I can't help with that just yet.")
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["locale"] == "en-AU"
    assert (
        context.attributes[TURN_DEBUG_METADATA_KEY]["locale_fallback_reason"]
        == "unsupported_locale_defaulted_to_english"
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["requested_locale"] == "fr-FR"


def test_graph_orchestrator_marks_swallowed_skill_errors_as_fallback() -> None:
    registry = InMemorySkillRegistry()
    registry.register(
        Skill(
            spec=SkillSpec(
                skill_id="dog_profile",
                description="Exploding dog profile create",
                tool_ids=[DOG_PROFILE_CREATE_TOOL_ID],
            ),
            tools=[ExplodingCreateTool()],
        )
    )
    observability = FakeObservability()
    orchestrator = build_orchestrator(
        skill_registry=registry,
        observability=observability,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-3"))

    try:
        context = orchestrator.run("session-3", "My dog is Peanut")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith(
        "Sorry, something went wrong while I was processing that."
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert (
        context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"]
        == "skill_exception_swallowed"
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["skill_error"]["type"] == "domain_error"
    assert any(event_name == "orchestrator_dog_profile_error" for event_name, _ in observability.events)


def test_graph_orchestrator_swallowed_skill_error_does_not_crash_with_cloud_observability() -> None:
    registry = InMemorySkillRegistry()
    registry.register(
        Skill(
            spec=SkillSpec(
                skill_id="dog_profile",
                description="Exploding dog profile create",
                tool_ids=[DOG_PROFILE_CREATE_TOOL_ID],
            ),
            tools=[ExplodingCreateTool()],
        )
    )
    orchestrator = build_orchestrator(
        skill_registry=registry,
        observability=CloudObservability(),
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-4"))

    try:
        context = orchestrator.run("session-4", "My dog is Peanut")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"] == "skill_exception_swallowed"
    assert context.attributes["last_response"].startswith(
        "Sorry, something went wrong while I was processing that."
    )


def test_graph_orchestrator_uses_knowledge_base_answer_before_static_fallback() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="hit",
            answer="Feed adult dogs twice daily.",
            confidence=0.91,
            sources=["Tailmate Feeding Guide"],
        )
    )
    orchestrator = build_orchestrator(
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-knowledge-hit"))

    try:
        context = orchestrator.run("session-knowledge-hit", "How often should I feed my dog?")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith("Feed adult dogs twice daily.")
    assert "Tailmate Feeding Guide" in context.attributes["last_response"]
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "knowledge_base.answer"
    assert context.attributes[KNOWLEDGE_BASE_RESULT_METADATA_KEY]["status"] == "hit"
    assert knowledge_retriever.requests == [("How often should I feed my dog?", "en-AU", None)]


def test_graph_orchestrator_returns_knowledge_base_out_of_scope_message() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="out_of_scope",
            confidence=0.88,
            sources=["Tailmate Feeding Guide"],
        )
    )
    orchestrator = build_orchestrator(
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-knowledge-oos"))

    try:
        context = orchestrator.run("session-knowledge-oos", "Can you diagnose this tumour?")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"] == (
        "This question is outside the Tailmate verified knowledge base. "
        "Please consult a vet."
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert (
        context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"]
        == "knowledge_base.out_of_scope"
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"] is None


def test_graph_orchestrator_falls_back_when_knowledge_base_misses_or_errors() -> None:
    observability = FakeObservability()
    miss_orchestrator = build_orchestrator(
        observability=observability,
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
    )
    miss_token = set_current_context(RuntimeRequestContext(session_id="session-knowledge-miss"))

    try:
        miss_context = miss_orchestrator.run("session-knowledge-miss", "hello")
    finally:
        reset_current_context(miss_token)

    assert miss_context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert miss_context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"] == "fallback.greeting"

    error_orchestrator = build_orchestrator(
        observability=observability,
        knowledge_retriever=FakeKnowledgeRetriever(error=RuntimeError("boom")),
    )
    error_token = set_current_context(RuntimeRequestContext(session_id="session-knowledge-error"))

    try:
        error_context = error_orchestrator.run("session-knowledge-error", "hello")
    finally:
        reset_current_context(error_token)

    assert error_context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert error_context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"] == "fallback.greeting"
    assert any(
        event_name == "orchestrator_knowledge_base_error"
        for event_name, _payload in observability.events
    )


def test_graph_orchestrator_uses_llm_generated_fallback_for_open_question_with_kb_miss() -> None:
    observability = FakeObservability()
    responder = FakeConversationalResponder(
        text="Puppies usually need smaller, more frequent meals.",
        provenance="llm_generated",
    )
    orchestrator = build_orchestrator(
        observability=observability,
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-llm-miss"))

    try:
        context = orchestrator.run("session-llm-miss", "How often should I feed a puppy?")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith(
        "Puppies usually need smaller, more frequent meals."
    )
    assert "has not been verified by Tailmate" in context.attributes["last_response"]
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_provenance"] == "llm_generated"
    assert responder.requests
    assert any(
        event_name == "orchestrator_conversational_fallback"
        for event_name, _payload in observability.events
    )


def test_graph_orchestrator_stream_run_uses_incremental_conversational_fallback() -> None:
    responder = StreamingConversationalResponder(
        chunks=("General dog-health ", "guidance."),
    )
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-stream-open"))

    try:
        events = list(
            orchestrator.stream_run(
                "session-stream-open",
                "What does lethargy in dogs usually indicate?",
            )
        )
    finally:
        reset_current_context(token)

    delta_events = [event for event in events if event["event"] == "query.delta"]
    assert [event["delta"] for event in delta_events][:2] == [
        "General dog-health ",
        "guidance.",
    ]
    assert responder.stream_requests
    assert responder.generate_calls == 0
    assert events[-1]["event"] == "query.completed"
    assert events[-1]["output"]["response"].startswith("General dog-health guidance.")


def test_graph_orchestrator_uses_llm_with_kb_scope_for_open_question_with_kb_out_of_scope() -> None:
    responder = FakeConversationalResponder(
        text="Lethargy in dogs can be associated with pain, illness, stress, or recovery needs.",
        provenance="llm_with_kb_scope",
    )
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="out_of_scope")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-llm-oos"))

    try:
        context = orchestrator.run("session-llm-oos", "What does lethargy in dogs usually indicate?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_provenance"] == "llm_with_kb_scope"
    assert "has not been verified by Tailmate" in context.attributes["last_response"]
    assert responder.requests


def test_graph_orchestrator_keeps_verified_kb_answers_without_disclaimer() -> None:
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(
            KnowledgeQueryOutput(
                status="hit",
                answer="Adult dogs usually eat twice daily.",
                confidence=0.87,
                sources=["Tailmate Feeding Guide"],
            )
        ),
        conversational_responder=FakeConversationalResponder(),
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-kb-verified"))

    try:
        context = orchestrator.run("session-kb-verified", "How often should I feed my dog?")
    finally:
        reset_current_context(token)

    assert "has not been verified by Tailmate" not in context.attributes["last_response"]
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_provenance"] == "kb_verified"


def test_graph_orchestrator_falls_back_to_template_when_conversational_responder_errors() -> None:
    observability = FakeObservability()
    orchestrator = build_orchestrator(
        observability=observability,
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
        conversational_responder=FakeConversationalResponder(error=RuntimeError("boom")),
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-llm-error"))

    try:
        context = orchestrator.run("session-llm-error", "How often should I feed a puppy?")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith("I can't help with that just yet.")
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_provenance"] == "deterministic"
    assert any(
        event_name == "orchestrator_conversational_fallback_error"
        for event_name, _payload in observability.events
    )


def test_graph_orchestrator_keeps_kb_out_of_scope_guidance_when_conversational_responder_errors() -> None:
    observability = FakeObservability()
    orchestrator = build_orchestrator(
        observability=observability,
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="out_of_scope")),
        conversational_responder=FakeConversationalResponder(error=RuntimeError("boom")),
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-llm-oos-error"))

    try:
        context = orchestrator.run(
            "session-llm-oos-error",
            "What does lethargy in dogs usually indicate?",
        )
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith(
        "This question is outside the Tailmate verified knowledge base."
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert (
        context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"]
        == "knowledge_base.out_of_scope"
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_provenance"] == "deterministic"
    assert any(
        event_name == "orchestrator_conversational_fallback_error"
        for event_name, _payload in observability.events
    )


def test_graph_orchestrator_uses_safety_redirect_for_diagnosis_request() -> None:
    responder = FakeConversationalResponder()
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="out_of_scope")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-llm-diagnosis"))

    try:
        context = orchestrator.run("session-llm-diagnosis", "Can you diagnose this tumour?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "llm.safety_redirect"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_provenance"] == "deterministic"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["safety_boundary_hit"] is True
    assert responder.requests == []


def test_graph_orchestrator_returns_safety_redirect_without_calling_llm_for_emergency() -> None:
    responder = FakeConversationalResponder()
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-safety-emergency"))

    try:
        context = orchestrator.run("session-safety-emergency", "My dog ate rat poison, what should I do?")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith(
        "This sounds like it needs immediate veterinary attention."
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "llm.safety_redirect"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["safety_boundary_hit"] is True
    assert responder.requests == []


def test_graph_orchestrator_returns_safety_redirect_without_calling_llm_for_medication_dose() -> None:
    responder = FakeConversationalResponder()
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-safety-dose"))

    try:
        context = orchestrator.run("session-safety-dose", "How much ibuprofen can I give my dog?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "llm.safety_redirect"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["safety_boundary_hit"] is True
    assert responder.requests == []


def test_graph_orchestrator_prioritizes_safety_redirect_over_greeting_fallback() -> None:
    responder = FakeConversationalResponder()
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-safety-greeting"))

    try:
        context = orchestrator.run("session-safety-greeting", "Hi, my dog ate rat poison")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "llm.safety_redirect"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["safety_boundary_hit"] is True
    assert responder.requests == []


def test_graph_orchestrator_returns_safety_redirect_for_non_english_emergency_message() -> None:
    responder = FakeConversationalResponder()
    orchestrator = build_orchestrator(
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
        conversational_responder=responder,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-safety-zh"))

    try:
        context = orchestrator.run("session-safety-zh", "我的狗吃了老鼠药，我该怎么办？")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "llm.safety_redirect"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["safety_boundary_hit"] is True
    assert responder.requests == []


def test_graph_orchestrator_empty_enrich_result_falls_through_to_knowledge_base() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="hit",
            answer="Adult dogs usually eat twice daily.",
            confidence=0.87,
            sources=["Tailmate Feeding Guide"],
        )
    )
    registry = InMemorySkillRegistry()
    registry.register(
        Skill(
            spec=SkillSpec(
                skill_id="dog_profile",
                description="Dog profile enrich noop",
                tool_ids=["dog_profile.enrich"],
            ),
            tools=[EmptyEnrichTool()],
        )
    )
    session_store = FakeSessionStore()
    session_store.contexts["session-knowledge-after-enrich-noop"] = SessionContext(
        session_id="session-knowledge-after-enrich-noop",
        attributes={"dog_id": "dog-1"},
    )
    orchestrator = build_orchestrator(
        session_store=session_store,
        skill_registry=registry,
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-knowledge-after-enrich-noop",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )

    try:
        context = orchestrator.run(
            "session-knowledge-after-enrich-noop",
            "How often should I feed him?",
        )
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith("Adult dogs usually eat twice daily.")
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert knowledge_retriever.requests == [("How often should I feed him?", "en-AU", None)]


def test_graph_orchestrator_augments_short_referential_follow_up_for_knowledge_base() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="hit",
            answer="Mild cases can resolve with supportive care, but persistent coughing needs a vet.",
            confidence=0.84,
            sources=["Tailmate Respiratory Guide"],
        )
    )
    session_store = FakeSessionStore()
    session_store.contexts["session-kb-follow-up"] = SessionContext(
        session_id="session-kb-follow-up",
        turns=[
            {"role": "user", "message": "What is kennel cough?"},
            {
                "role": "assistant",
                "message": "Kennel cough is a contagious respiratory disease.",
                "source": "knowledge_base",
            },
        ],
    )
    orchestrator = build_orchestrator(
        session_store=session_store,
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-kb-follow-up"))

    try:
        context = orchestrator.run("session-kb-follow-up", "Is that serious?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert knowledge_retriever.requests == [
        (
            "[Prior context: Kennel cough is a contagious respiratory disease.]\n\nIs that serious?",
            "en-AU",
            None,
        )
    ]


def test_graph_orchestrator_does_not_augment_short_new_topic_questions() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="hit",
            answer="Parvovirus is a serious disease prevented by vaccination.",
            confidence=0.9,
            sources=["Tailmate Vaccination Guide"],
        )
    )
    session_store = FakeSessionStore()
    session_store.contexts["session-kb-new-topic"] = SessionContext(
        session_id="session-kb-new-topic",
        turns=[
            {"role": "user", "message": "What is kennel cough?"},
            {
                "role": "assistant",
                "message": "Kennel cough is a contagious respiratory disease.",
                "source": "knowledge_base",
            },
        ],
    )
    orchestrator = build_orchestrator(
        session_store=session_store,
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-kb-new-topic"))

    try:
        context = orchestrator.run("session-kb-new-topic", "Parvo?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert knowledge_retriever.requests == [("Parvo?", "en-AU", None)]


def test_graph_orchestrator_uses_recent_turn_history_for_dog_name_pronoun_resolution() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="hit",
            answer="Adult dogs usually eat twice daily.",
            confidence=0.87,
            sources=["Tailmate Feeding Guide"],
        )
    )
    session_store = FakeSessionStore()
    session_store.contexts["session-history-dog-context"] = SessionContext(
        session_id="session-history-dog-context",
        turns=[
            {"role": "user", "message": "My dog is Peanut."},
            {
                "role": "assistant",
                "message": "Thanks, I will remember Peanut for this chat.",
                "source": "fallback",
            },
        ],
    )
    orchestrator = build_orchestrator(
        session_store=session_store,
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-history-dog-context"))

    try:
        context = orchestrator.run("session-history-dog-context", "How often should I feed him?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert knowledge_retriever.requests == [
        (
            "[Prior context: Thanks, I will remember Peanut for this chat.]\n\nHow often should I feed him?",
            "en-AU",
            "Dog: Peanut.",
        )
    ]


def test_graph_orchestrator_uses_locale_specific_pronouns_for_history_dog_context() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="hit",
            answer="Adult dogs usually eat twice daily.",
            confidence=0.87,
            sources=["Tailmate Feeding Guide"],
        )
    )
    session_store = FakeSessionStore()
    session_store.contexts["session-history-dog-context-vi"] = SessionContext(
        session_id="session-history-dog-context-vi",
        turns=[{"role": "user", "message": "My dog is Peanut."}],
    )
    orchestrator = build_orchestrator(
        session_store=session_store,
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-history-dog-context-vi",
            metadata={"locale": "vi"},
        )
    )

    try:
        context = orchestrator.run(
            "session-history-dog-context-vi",
            "Nó có nên ăn hai bữa không?",
        )
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert knowledge_retriever.requests == [
        ("Nó có nên ăn hai bữa không?", "vi", "Dog: Peanut.")
    ]


def test_graph_orchestrator_recall_load_errors_fall_through_to_knowledge_base() -> None:
    knowledge_retriever = FakeKnowledgeRetriever(
        KnowledgeQueryOutput(
            status="hit",
            answer="Kennel cough is a contagious respiratory disease.",
            confidence=0.9,
            sources=["Tailmate Respiratory Guide"],
        )
    )
    session_store = FakeSessionStore()
    session_store.contexts["session-recall-error"] = SessionContext(
        session_id="session-recall-error",
        attributes={"dog_id": "dog-1"},
    )
    observability = FakeObservability()
    orchestrator = build_orchestrator(
        session_store=session_store,
        observability=observability,
        dog_profile_db_adapter=ExplodingRecallAdapter(),
        knowledge_retriever=knowledge_retriever,
    )
    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-recall-error",
            metadata={"user_id": "user-1"},
            user_id="user-1",
        )
    )

    try:
        context = orchestrator.run("session-recall-error", "What is kennel cough?")
    finally:
        reset_current_context(token)

    assert context.attributes["last_response"].startswith(
        "Kennel cough is a contagious respiratory disease."
    )
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
    assert any(
        event_name == "orchestrator_dog_profile_recall_error"
        for event_name, _payload in observability.events
    )


def test_graph_orchestrator_uses_profile_query_fallback_for_active_dog_questions() -> None:
    store = FakeSessionStore()
    store.contexts["session-profile-query"] = SessionContext(
        session_id="session-profile-query",
        attributes={"dog_id": "dog-1"},
    )
    orchestrator = build_orchestrator(
        session_store=store,
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-profile-query"))

    try:
        context = orchestrator.run("session-profile-query", "What breed is she?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"] == "fallback.profile_query"
    assert context.attributes["last_response"].startswith("I found your dog's profile")


def test_graph_orchestrator_uses_post_kb_followup_fallback_after_kb_turn() -> None:
    store = FakeSessionStore()
    store.contexts["session-post-kb-followup"] = SessionContext(
        session_id="session-post-kb-followup",
        turns=[
            {
                "role": "assistant",
                "message": "Feed adult dogs twice daily.\n\nSources: Guide",
                "source": "knowledge_base",
                "locale": "en-AU",
                "response_key": "knowledge_base.answer",
                "fallback_reason": None,
            }
        ],
    )
    orchestrator = build_orchestrator(
        session_store=store,
        knowledge_retriever=FakeKnowledgeRetriever(KnowledgeQueryOutput(status="miss")),
    )
    token = set_current_context(RuntimeRequestContext(session_id="session-post-kb-followup"))

    try:
        context = orchestrator.run("session-post-kb-followup", "What about that?")
    finally:
        reset_current_context(token)

    assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert (
        context.attributes[TURN_DEBUG_METADATA_KEY]["fallback_reason"]
        == "fallback.post_kb_followup"
    )
    assert context.attributes["last_response"].startswith("Could you tell me a bit more?")
