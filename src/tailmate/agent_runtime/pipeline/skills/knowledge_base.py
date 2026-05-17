"""Runtime skill for knowledge-base fallback routing."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.agent_runtime.pipeline.skill import IntentMatch
from tailmate.agent_runtime.pipeline.turn_context import AssistantTurn, SkillExecutionResult, TurnContext
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.knowledge_retriever import KnowledgeRetriever
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.services.turn_messages import (
    build_knowledge_base_answer,
    build_knowledge_base_out_of_scope,
    message_contains_question,
)
from tailmate.contracts.constants import DOG_PROFILE_ENRICH_TOOL_ID, KNOWLEDGE_BASE_RESULT_METADATA_KEY
from tailmate.contracts.errors import TailmateError
from tailmate.contracts.knowledge import KnowledgeQueryInput
from tailmate.metrics import record_kb_query

from ._shared import has_tool, is_recall_turn, resolve_dog_selection


@dataclass
class KnowledgeBaseRuntimeSkill:
    """Owns the catch-all knowledge-base routing decision."""

    skill_registry: SkillRegistry
    dog_profile_db_adapter: DogProfileDBAdapter | None = None
    knowledge_retriever: KnowledgeRetriever | None = None
    observability: Observability | None = None
    conversational_responder_available: bool = False
    skill_id: str = "knowledge_base"
    routing_description: str = (
        "User asks a general dog-care, behaviour, nutrition, or health question that is not "
        "just stored profile recall and may need knowledge-base or open-intent handling."
    )
    depends_on: tuple[str, ...] = (
        "dog_profile:create",
        "dog_profile:enrich",
        "dog_profile:recall",
    )

    def classify(self, ctx: TurnContext) -> IntentMatch | None:
        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        if (
            selection.active_dog_id is not None
            and not is_recall_turn(ctx, dog_profile_db_adapter=self.dog_profile_db_adapter)
            and has_tool(self.skill_registry, DOG_PROFILE_ENRICH_TOOL_ID)
            and message_contains_question(ctx.message)
        ):
            return IntentMatch(intent="known", priority=10)
        return IntentMatch(intent="open", priority=0)

    def execute(self, ctx: TurnContext) -> SkillExecutionResult:
        if self.knowledge_retriever is None:
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        try:
            result = self.knowledge_retriever.query(
                KnowledgeQueryInput(
                    user_message=ctx.effective_knowledge_message,
                    locale=ctx.locale,
                    dog_context=ctx.dog_context,
                )
            )
            if self.observability is not None:
                self.observability.info(
                    "orchestrator_knowledge_base",
                    session_id=ctx.session_id,
                    status=result.status,
                    confidence=result.confidence,
                    source_count=len(result.sources),
                    locale=ctx.locale,
                )
            record_kb_query(status=result.status)
            payload = result.model_dump(mode="json")
            if result.status == "miss":
                payload["open_intent_scope"] = "kb_miss"
            elif result.status == "out_of_scope":
                payload["open_intent_scope"] = "kb_out_of_scope"
                fallback = build_knowledge_base_out_of_scope(locale=ctx.locale)
                payload["open_intent_fallback"] = {
                    "message": fallback.text,
                    "source": "knowledge_base",
                    "response_key": fallback.key,
                    "response_provenance": "deterministic",
                }
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome=result.status,
                payload=payload,
            )
        except TailmateError as exc:
            if self.observability is not None:
                self.observability.error(
                    "orchestrator_knowledge_base_error",
                    session_id=ctx.session_id,
                    error_type=exc.error_type,
                    error_message=str(exc),
                )
            record_kb_query(status="error")
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="error",
                payload={"open_intent_scope": "error"},
                error={"type": exc.error_type, "message": str(exc)},
            )
        except Exception as exc:
            if self.observability is not None:
                self.observability.error(
                    "orchestrator_knowledge_base_error",
                    session_id=ctx.session_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            record_kb_query(status="error")
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="error",
                payload={"open_intent_scope": "error"},
                error={"type": type(exc).__name__, "message": "Unexpected internal failure."},
            )

    def apply_context(self, ctx: TurnContext, result: SkillExecutionResult) -> None:
        if result.outcome not in {"hit", "out_of_scope", "miss"}:
            return
        ctx.knowledge_result = type(
            "KnowledgeResultProxy",
            (),
            {
                **result.payload,
                "model_dump": lambda self, mode="json": dict(result.payload),
            },
        )()
        ctx.session.attributes[KNOWLEDGE_BASE_RESULT_METADATA_KEY] = dict(result.payload)

    def assemble(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        if result.outcome == "hit":
            message = build_knowledge_base_answer(
                locale=ctx.locale,
                answer=str(result.payload["answer"]),
                sources=list(result.payload.get("sources") or []),
            )
            provenance = "kb_verified"
        elif result.outcome == "out_of_scope":
            if (
                ctx.intent is not None
                and ctx.intent.intent == "open"
                and self.conversational_responder_available
            ):
                return None
            message = build_knowledge_base_out_of_scope(locale=ctx.locale)
            provenance = "deterministic"
        else:
            return None
        return AssistantTurn(
            message=message.text,
            source="knowledge_base",
            response_key=message.key,
            skill_results=tuple(ctx.skill_results),
            response_provenance=provenance,
        )

    def assemble_open_intent_fallback(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        if result.outcome != "out_of_scope":
            return None
        message = build_knowledge_base_out_of_scope(locale=ctx.locale)
        return AssistantTurn(
            message=message.text,
            source="knowledge_base",
            response_key=message.key,
            skill_results=tuple(ctx.skill_results),
            response_provenance="deterministic",
        )
