from __future__ import annotations

import time
from datetime import datetime, timezone

from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.models.skill_spec import SkillSpec
from tailmate.agent_runtime.pipeline.skills import register_standard_runtime_skills
from tailmate.agent_runtime.pipeline.steps.skill_execution_step import SkillExecutionStep
from tailmate.agent_runtime.pipeline.turn_context import (
    DogProfileTurnResult,
    IntentClassification,
    SkillExecutionResult,
    TurnContext,
)
from tailmate.contracts.dog_profile import CreateDogProfileOutput, DogProfile, EnrichDogProfileOutput
from tailmate.metrics import render_prometheus_metrics, reset_metrics_registry
from tailmate.skills.base import Skill
from tailmate.skills.registry import InMemorySkillRegistry


class FakeObservability:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event_name: str, **kwargs: object) -> None:
        self.events.append((event_name, kwargs))

    def error(self, event_name: str, **kwargs: object) -> None:
        self.events.append((event_name, kwargs))


class FakeCreateTool:
    name = "dog_profile.create"

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        return CreateDogProfileOutput(
            dog_id="dog-1",
            profile_summary=str(payload["name"]),
            created_at=datetime.now(timezone.utc),
        ).model_dump(mode="json")


class FakeEnrichTool:
    name = "dog_profile.enrich"

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        return EnrichDogProfileOutput(
            updated_fields={"medical_history": ["recent cough"]},
            raw_note=None,
            extraction_strategy_used="rule",
        ).model_dump(mode="json")


class FakeKnowledgeRetriever:
    def query(self, request):
        return type(
            "KnowledgeResult",
            (),
            {
                "status": "hit",
                "answer": "Feed twice daily.",
                "confidence": 0.9,
                "sources": ["Guide"],
                "model_dump": lambda self, mode="json": {
                    "status": "hit",
                    "answer": "Feed twice daily.",
                    "confidence": 0.9,
                    "sources": ["Guide"],
                },
            },
        )()


class SlowStripTool:
    name = "strip_metadata.upload"

    def invoke(self, payload: dict[str, object]) -> dict[str, object]:
        time.sleep(0.2)
        return {
            "resource_uri": "file:///tmp/dog-1.jpg",
            "logical_path": "dogs/dog-1/images/media-1.jpg",
            "media_kind": "image",
        }


class FakeDogProfileAdapter:
    def load_profile(self, dog_id: str, *, requesting_user_id: str):
        return DogProfile(
            dog_id=dog_id,
            user_id=requesting_user_id,
            name="Buddy",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


class SlowDogProfileAdapter(FakeDogProfileAdapter):
    def load_profile(self, dog_id: str, *, requesting_user_id: str):
        time.sleep(0.2)
        return super().load_profile(dog_id, requesting_user_id=requesting_user_id)


class LegacyRuntimeSkill:
    skill_id = "legacy"
    depends_on = ()

    def classify(self, ctx):
        return None

    def execute(self, ctx):
        return SkillExecutionResult(skill_id=self.skill_id, outcome="success", payload={})

    def assemble(self, ctx, result):
        return None


def _build_registry(observability: FakeObservability) -> InMemorySkillRegistry:
    reset_metrics_registry()
    registry = InMemorySkillRegistry()
    registry.register(
        Skill(
            spec=SkillSpec(
                skill_id="dog_profile",
                description="Dog profile",
                tool_ids=["dog_profile.create", "dog_profile.enrich"],
            ),
            tools=[FakeCreateTool(), FakeEnrichTool()],
        )
    )
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
        knowledge_retriever=FakeKnowledgeRetriever(),
        observability=observability,
    )
    return registry


def _build_parallel_registry(observability: FakeObservability) -> InMemorySkillRegistry:
    reset_metrics_registry()
    registry = InMemorySkillRegistry()
    registry.register(
        Skill(
            spec=SkillSpec(
                skill_id="dog_profile",
                description="Dog profile",
                tool_ids=[],
            ),
            tools=[],
        )
    )
    registry.register(
        Skill(
            spec=SkillSpec(
                skill_id="strip_metadata",
                description="Strip metadata",
                tool_ids=["strip_metadata.upload"],
            ),
            tools=[SlowStripTool()],
        )
    )
    register_standard_runtime_skills(
        registry,
        dog_profile_db_adapter=SlowDogProfileAdapter(),
        observability=observability,
    )
    return registry


def test_skill_execution_step_records_duration_and_emits_per_skill_event() -> None:
    observability = FakeObservability()
    ctx = TurnContext(
        session=SessionContext(session_id="session-1", attributes={"dog_id": "dog-1"}),
        session_id="session-1",
        message="He had a cough last week, should I be worried?",
        locale="en-AU",
        locale_resolution=None,
        request_metadata={"user_id": "user-1"},
        strip_request=None,
        intent=IntentClassification(
            intent="known",
            matched_skills=("dog_profile:enrich", "knowledge_base"),
        ),
    )

    SkillExecutionStep(
        skill_registry=_build_registry(observability),
        observability=observability,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
        knowledge_retriever=FakeKnowledgeRetriever(),
    ).run(ctx)

    assert ctx.execution_phase_started_at is not None
    assert [result.skill_id for result in ctx.skill_results] == [
        "dog_profile:enrich",
        "knowledge_base",
    ]
    assert all(result.duration_ms is not None for result in ctx.skill_results)
    assert any(event_name == "orchestrator_skill_executed" for event_name, _ in observability.events)
    assert ctx.session.attributes["dog_id"] == "dog-1"
    assert ctx.session.attributes["knowledge_base"]["answer"] == "Feed twice daily."
    assert ctx.updated_fields == ["medical_history"]
    assert ctx.dog_profile_result is not None
    assert ctx.dog_profile_result.outcome == "enrich"
    assert ctx.skill_attempted == ["dog_profile:enrich", "knowledge_base"]
    metrics_payload = render_prometheus_metrics()
    assert 'tailmate_skill_invocations_total{skill="dog_profile:enrich",status="enrich"} 1' in metrics_payload
    assert 'tailmate_skill_invocations_total{skill="knowledge_base",status="hit"} 1' in metrics_payload
    assert 'tailmate_kb_queries_total{status="hit"} 1' in metrics_payload


def test_skill_execution_step_persists_created_dog_id_into_session() -> None:
    observability = FakeObservability()
    ctx = TurnContext(
        session=SessionContext(session_id="session-create", attributes={}),
        session_id="session-create",
        message="我的豆豆是一只法国斗牛犬，4岁，体重4公斤",
        locale="zh-Hans",
        locale_resolution=None,
        request_metadata={"user_id": "user-1"},
        strip_request=None,
        intent=IntentClassification(
            intent="known",
            matched_skills=("dog_profile:create",),
        ),
    )

    SkillExecutionStep(
        skill_registry=_build_registry(observability),
        observability=observability,
        dog_profile_db_adapter=FakeDogProfileAdapter(),
        knowledge_retriever=FakeKnowledgeRetriever(),
    ).run(ctx)

    assert [result.skill_id for result in ctx.skill_results] == ["dog_profile:create"]
    assert ctx.session.attributes["dog_id"] == "dog-1"
    assert ctx.dog_profile_result is not None
    assert ctx.dog_profile_result.outcome == "create"
    assert ctx.skill_attempted == ["dog_profile:create"]
    metrics_payload = render_prometheus_metrics()
    assert 'tailmate_skill_invocations_total{skill="dog_profile:create",status="create"} 1' in metrics_payload


def test_skill_execution_step_runs_independent_skills_in_parallel() -> None:
    observability = FakeObservability()
    ctx = TurnContext(
        session=SessionContext(session_id="session-2", attributes={"dog_id": "dog-1"}),
        session_id="session-2",
        message="Recall and sanitize",
        locale="en-AU",
        locale_resolution=None,
        request_metadata={"user_id": "user-1"},
        strip_request={"dog_id": "dog-1", "resource_kind": "images", "filename": "dog.jpg", "content_type": "image/jpeg", "payload_base64": "Zm9v"},
        intent=IntentClassification(
            intent="known",
            matched_skills=("strip_metadata", "dog_profile:recall"),
        ),
    )

    started_at = time.monotonic()
    SkillExecutionStep(
        skill_registry=_build_parallel_registry(observability),
        observability=observability,
        dog_profile_db_adapter=SlowDogProfileAdapter(),
        knowledge_retriever=None,
    ).run(ctx)
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.39
    assert any(
        event_name == "orchestrator_turn_parallel_skills"
        for event_name, _ in observability.events
    )
    metrics_payload = render_prometheus_metrics()
    assert 'tailmate_skill_invocations_total{skill="strip_metadata",status="success"} 1' in metrics_payload
    assert 'tailmate_skill_invocations_total{skill="dog_profile:recall",status="recall"} 1' in metrics_payload


def test_skill_execution_step_skips_apply_context_for_legacy_runtime_skills() -> None:
    observability = FakeObservability()
    registry = InMemorySkillRegistry()
    registry.register_runtime_skill(LegacyRuntimeSkill())
    ctx = TurnContext(
        session=SessionContext(session_id="session-3", attributes={}),
        session_id="session-3",
        message="hello",
        locale="en-AU",
        locale_resolution=None,
        request_metadata={},
        strip_request=None,
        intent=IntentClassification(intent="known", matched_skills=("legacy",)),
        dog_profile_result=DogProfileTurnResult(outcome="noop"),
    )

    SkillExecutionStep(
        skill_registry=registry,
        observability=observability,
        dog_profile_db_adapter=None,
        knowledge_retriever=None,
    ).run(ctx)

    assert [result.skill_id for result in ctx.skill_results] == ["legacy"]
