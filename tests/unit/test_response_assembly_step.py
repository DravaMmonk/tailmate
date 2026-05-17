from __future__ import annotations

from datetime import datetime, timezone

from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.pipeline.skills import register_standard_runtime_skills
from tailmate.agent_runtime.pipeline.steps.response_assembly_step import ResponseAssemblyStep
from tailmate.agent_runtime.pipeline.turn_context import (
    IntentClassification,
    SkillExecutionResult,
    TurnContext,
)
from tailmate.contracts.dog_profile import DogProfile
from tailmate.skills.registry import InMemorySkillRegistry


class FakeObservability:
    def __init__(self) -> None:
        self.errors: list[tuple[str, dict[str, object]]] = []

    def info(self, event_name: str, **kwargs: object) -> None:
        return None

    def error(self, event_name: str, **kwargs: object) -> None:
        self.errors.append((event_name, kwargs))


class ExplodingConversationalResponder:
    def generate(self, request):
        raise RuntimeError("boom")


class StreamingConversationalResponder:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def stream_generate(self, request):
        self.requests.append(request)
        yield "General dog-health "
        yield "guidance."


def _build_context(
    *,
    message: str = "hello",
    skill_results: list[SkillExecutionResult],
    session_attributes: dict[str, object] | None = None,
) -> TurnContext:
    return TurnContext(
        session=SessionContext(session_id="session-1", attributes=session_attributes or {}),
        session_id="session-1",
        message=message,
        locale="en-AU",
        locale_resolution=None,
        request_metadata={},
        strip_request=None,
        skill_results=skill_results,
    )


def _build_registry(*, conversational_responder_available: bool = False) -> InMemorySkillRegistry:
    registry = InMemorySkillRegistry()
    register_standard_runtime_skills(
        registry,
        conversational_responder_available=conversational_responder_available,
    )
    return registry


def test_response_assembly_prioritizes_strip_metadata() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="strip_metadata",
                outcome="success",
                payload={"resource_uri": "file:///tmp/dog.jpg"},
            )
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "skill:strip_metadata"
    assert ctx.assistant_turn.response_key == "strip_metadata.success"


def test_response_assembly_prioritizes_create_confirmation() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="dog_profile:create",
                outcome="create",
                payload={"created_name": "Buddy"},
            )
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "skill:dog_profile:create"
    assert ctx.assistant_turn.response_key == "dog_profile.create_confirmation"


def test_response_assembly_builds_enrich_and_hit_answer() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="dog_profile:enrich",
                outcome="enrich",
                payload={"updated_fields": {"medical_history": ["recent cough"]}, "raw_note_present": False},
            ),
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="hit",
                payload={"answer": "See a vet if it returns.", "sources": ["Guide"]},
            ),
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "skill:dog_profile:enrich+knowledge_base"
    assert ctx.assistant_turn.response_key == "dog_profile.enrich_and_answer"


def test_response_assembly_builds_enrich_and_out_of_scope_answer() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="dog_profile:enrich",
                outcome="enrich",
                payload={"updated_fields": {"medical_history": ["recent cough"]}, "raw_note_present": False},
            ),
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="out_of_scope",
                payload={"sources": ["Guide"]},
            ),
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.response_key == "dog_profile.enrich_and_answer"


def test_response_assembly_builds_plain_enrich_confirmation() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="dog_profile:enrich",
                outcome="enrich",
                payload={"updated_fields": {"medical_history": ["recent cough"]}, "raw_note_present": False},
            )
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "skill:dog_profile:enrich"


def test_response_assembly_builds_recall_summary() -> None:
    now = datetime.now(timezone.utc)
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="dog_profile:recall",
                outcome="recall",
                payload={
                    "profile": {
                        "dog_id": "dog-1",
                        "user_id": "user-1",
                        "name": "Buddy",
                        "breed": "Corgi",
                        "created_at": now,
                        "updated_at": now,
                    }
                },
            )
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "memory:dog_profile"


def test_response_assembly_builds_knowledge_base_hit() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="hit",
                payload={"answer": "Feed twice daily.", "sources": ["Guide"]},
            )
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "knowledge_base"
    assert ctx.assistant_turn.response_key == "knowledge_base.answer"


def test_response_assembly_builds_knowledge_base_out_of_scope() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="out_of_scope",
                payload={"sources": ["Guide"]},
            )
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.response_key == "knowledge_base.out_of_scope"


def test_response_assembly_builds_skill_error_message() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="dog_profile:enrich",
                outcome="error",
                payload={},
                error={"type": "domain_error", "message": "boom"},
            )
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "fallback"
    assert ctx.assistant_turn.fallback_reason == "skill_exception_swallowed"


def test_response_assembly_prefers_later_success_over_earlier_skill_error() -> None:
    ctx = _build_context(
        skill_results=[
            SkillExecutionResult(
                skill_id="dog_profile:enrich",
                outcome="error",
                payload={},
                error={"type": "domain_error", "message": "boom"},
            ),
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="hit",
                payload={"answer": "Feed twice daily.", "sources": ["Guide"]},
            ),
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "knowledge_base"
    assert ctx.assistant_turn.response_key == "knowledge_base.answer"


def test_response_assembly_builds_fallback_when_no_skill_matches() -> None:
    ctx = _build_context(
        message="hello",
        skill_results=[],
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "fallback"
    assert ctx.assistant_turn.response_key == "fallback.greeting"


def test_response_assembly_uses_returning_greeting_when_dog_name_is_known() -> None:
    ctx = _build_context(
        message="hello",
        skill_results=[],
    )
    ctx.session.turns.extend(
        [
            {"role": "user", "message": "My dog Mochi is a desexed female French Bulldog."},
            {"role": "assistant", "message": "Created a profile for Mochi!"},
            {"role": "user", "message": "hello"},
        ]
    )

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "fallback"
    assert ctx.assistant_turn.response_key == "fallback.greeting_returning"
    assert ctx.assistant_turn.message == "Welcome back! How can I help with Mochi today?"


def test_response_assembly_uses_current_profile_for_returning_greeting() -> None:
    ctx = _build_context(
        message="hello",
        skill_results=[],
        session_attributes={"dog_id": "dog-1"},
    )
    ctx.current_dog_profile = DogProfile(dog_id="dog-1", user_id="user-1", name="Buddy")

    ResponseAssemblyStep(_build_registry()).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.response_key == "fallback.greeting_returning"
    assert ctx.assistant_turn.message == "Welcome back! How can I help with Buddy today?"


def test_response_assembly_keeps_kb_out_of_scope_when_conversational_fallback_errors() -> None:
    observability = FakeObservability()
    ctx = _build_context(
        message="What does lethargy in dogs usually indicate?",
        skill_results=[
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="out_of_scope",
                payload={"sources": ["Guide"]},
            )
        ],
    )
    ctx.intent = IntentClassification(intent="open", matched_skills=("knowledge_base",))

    ResponseAssemblyStep(
        _build_registry(conversational_responder_available=True),
        conversational_responder=ExplodingConversationalResponder(),
        observability=observability,
    ).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "knowledge_base"
    assert ctx.assistant_turn.response_key == "knowledge_base.out_of_scope"
    assert ctx.assistant_turn.response_provenance == "deterministic"
    assert observability.errors[0][0] == "orchestrator_conversational_fallback_error"


def test_response_assembly_uses_safety_redirect_before_conversational_fallback() -> None:
    ctx = _build_context(
        message="How much ibuprofen can I give my dog?",
        skill_results=[
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="miss",
                payload={},
            )
        ],
    )
    ctx.intent = IntentClassification(intent="open", matched_skills=("knowledge_base",))

    ResponseAssemblyStep(
        _build_registry(conversational_responder_available=True),
        conversational_responder=ExplodingConversationalResponder(),
        observability=FakeObservability(),
    ).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.source == "fallback"
    assert ctx.assistant_turn.response_key == "llm.safety_redirect"
    assert ctx.safety_boundary_hit is True


def test_response_assembly_uses_safety_redirect_before_greeting_fallback() -> None:
    ctx = _build_context(
        message="Hi, my dog ate rat poison",
        skill_results=[
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="miss",
                payload={},
            )
        ],
    )
    ctx.intent = IntentClassification(intent="open", matched_skills=("knowledge_base",))

    ResponseAssemblyStep(
        _build_registry(conversational_responder_available=True),
        conversational_responder=ExplodingConversationalResponder(),
        observability=FakeObservability(),
    ).run(ctx)

    assert ctx.assistant_turn is not None
    assert ctx.assistant_turn.response_key == "llm.safety_redirect"
    assert ctx.safety_boundary_hit is True


def test_response_assembly_streams_conversational_fallback_chunks() -> None:
    responder = StreamingConversationalResponder()
    ctx = _build_context(
        message="What does lethargy in dogs usually indicate?",
        skill_results=[
            SkillExecutionResult(
                skill_id="knowledge_base",
                outcome="miss",
                payload={},
            )
        ],
    )
    ctx.intent = IntentClassification(intent="open", matched_skills=("knowledge_base",))

    step = ResponseAssemblyStep(
        _build_registry(conversational_responder_available=True),
        conversational_responder=responder,
        observability=FakeObservability(),
    )

    assert step.can_stream_conversational_fallback(ctx) is True

    stream = step.stream_conversational_fallback(ctx)
    chunks: list[str] = []
    while True:
        try:
            chunks.append(next(stream))
        except StopIteration as stop:
            assistant_turn = stop.value
            break

    assert "".join(chunks).startswith("General dog-health guidance.")
    assert assistant_turn is not None
    assert assistant_turn.source == "llm:conversational"
    assert assistant_turn.response_provenance == "llm_generated"
    assert assistant_turn.message == "".join(chunks)
