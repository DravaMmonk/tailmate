"""Runtime skill for dog-profile enrichment routing."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.adapters.dog_profile.extractors import looks_like_dog_profile_trigger
from tailmate.agent_runtime.pipeline.steps._tool_finder import find_tool
from tailmate.agent_runtime.pipeline.skill import IntentMatch
from tailmate.agent_runtime.pipeline.turn_context import (
    AssistantTurn,
    DogProfileTurnResult,
    SkillExecutionResult,
    TurnContext,
)
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.services.turn_messages import (
    build_enrich_and_answer_message,
    build_enrich_confirmation,
    build_knowledge_base_answer,
    build_knowledge_base_out_of_scope,
    build_skill_error_message,
    message_contains_question,
)
from tailmate.contracts.constants import DOG_PROFILE_ENRICH_TOOL_ID, DOG_PROFILE_RESULT_METADATA_KEY
from tailmate.contracts.errors import DomainError, TailmateError

from ._shared import (
    find_result,
    has_tool,
    is_recall_turn,
    persist_active_dog,
    resolve_dog_selection,
)


@dataclass
class DogProfileEnrichRuntimeSkill:
    """Owns dog-profile enrichment routing decisions."""

    skill_registry: SkillRegistry
    dog_profile_db_adapter: DogProfileDBAdapter | None = None
    observability: Observability | None = None
    skill_id: str = "dog_profile:enrich"
    routing_description: str = (
        "User adds or updates facts about the active dog, including health notes, symptoms, "
        "measurements, behaviour, or other profile details."
    )
    depends_on: tuple[str, ...] = ()

    def classify(self, ctx: TurnContext) -> IntentMatch | None:
        if ctx.strip_request is not None:
            return None
        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        if selection.active_dog_id is None:
            return None
        if is_recall_turn(ctx, dog_profile_db_adapter=self.dog_profile_db_adapter):
            return None
        if not has_tool(self.skill_registry, DOG_PROFILE_ENRICH_TOOL_ID):
            return None
        if not (
            message_contains_question(ctx.message)
            or looks_like_dog_profile_trigger(ctx.message)
        ):
            return None
        return IntentMatch(intent="known", priority=60)

    def execute(self, ctx: TurnContext) -> SkillExecutionResult:
        tool = find_tool(self.skill_registry, DOG_PROFILE_ENRICH_TOOL_ID)
        if tool is None:
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        if selection.active_dog_id is None:
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        try:
            verified_user_id = str(ctx.request_metadata.get("user_id", "")).strip()
            if not verified_user_id:
                raise DomainError("Missing verified user_id in request metadata.")
            enrich_result = tool.invoke(
                {
                    "dog_id": selection.active_dog_id,
                    "requesting_user_id": verified_user_id,
                    "user_message": ctx.message,
                }
            )
            updated_fields = tuple(sorted((enrich_result.get("updated_fields") or {}).keys()))
            raw_note_present = bool(enrich_result.get("raw_note"))
            if updated_fields or raw_note_present:
                if self.observability is not None:
                    self.observability.info(
                        "orchestrator_dog_profile_enrich",
                        session_id=ctx.session_id,
                        dog_id=selection.active_dog_id,
                        updated_fields=list(updated_fields),
                        strategy=enrich_result.get("extraction_strategy_used"),
                    )
                return SkillExecutionResult(
                    skill_id=self.skill_id,
                    outcome="enrich",
                    payload={
                        "dog_id": selection.active_dog_id,
                        "updated_fields": list(updated_fields),
                        "raw_note_present": raw_note_present,
                        **dict(enrich_result),
                    },
                )
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="noop",
                payload={"dog_id": selection.active_dog_id},
            )
        except TailmateError as exc:
            if self.observability is not None:
                self.observability.error(
                    "orchestrator_dog_profile_error",
                    session_id=ctx.session_id,
                    error_type=exc.error_type,
                    error_message=str(exc),
                )
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="error",
                payload={},
                error={"type": exc.error_type, "message": str(exc)},
            )
        except Exception as exc:
            if self.observability is not None:
                self.observability.error(
                    "orchestrator_dog_profile_error",
                    session_id=ctx.session_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="error",
                payload={},
                error={"type": type(exc).__name__, "message": "Unexpected internal failure."},
            )

    def apply_context(self, ctx: TurnContext, result: SkillExecutionResult) -> None:
        if result.outcome == "enrich":
            updated_fields = tuple(result.payload.get("updated_fields") or [])
            raw_note_present = bool(result.payload.get("raw_note_present"))
            ctx.updated_fields = list(updated_fields)
            ctx.raw_note_saved = raw_note_present
            persist_active_dog(ctx.session.attributes, str(result.payload["dog_id"]))
            ctx.session.attributes[DOG_PROFILE_RESULT_METADATA_KEY] = {
                "action": "enrich",
                "dog_id": result.payload["dog_id"],
                "updated_fields": dict(result.payload.get("updated_fields") or {}),
                "raw_note": result.payload.get("raw_note"),
                "extraction_strategy_used": result.payload.get("extraction_strategy_used"),
            }
            ctx.dog_profile_result = DogProfileTurnResult(
                outcome="enrich",
                updated_fields=updated_fields,
                raw_note_present=raw_note_present,
                attempted_tools=tuple(ctx.skill_attempted),
            )
            return
        if result.outcome == "error":
            ctx.skill_error = result.error
            ctx.dog_profile_result = DogProfileTurnResult(
                outcome="error",
                attempted_tools=tuple(ctx.skill_attempted),
                skill_error=result.error,
            )

    def assemble(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        if result.outcome == "error":
            message = build_skill_error_message(locale=ctx.locale)
            return AssistantTurn(
                message=message.text,
                source="fallback",
                response_key=message.key,
                skill_results=tuple(ctx.skill_results),
                response_provenance="deterministic",
                fallback_reason="skill_exception_swallowed",
            )
        if result.outcome != "enrich":
            return None

        knowledge_result = find_result(ctx, "knowledge_base")
        if knowledge_result is not None and knowledge_result.outcome in {"hit", "out_of_scope"}:
            if knowledge_result.outcome == "hit":
                kb_message = build_knowledge_base_answer(
                    locale=ctx.locale,
                    answer=str(knowledge_result.payload["answer"]),
                    sources=list(knowledge_result.payload.get("sources") or []),
                )
            else:
                kb_message = build_knowledge_base_out_of_scope(locale=ctx.locale)

            message = build_enrich_and_answer_message(
                locale=ctx.locale,
                updated_fields=tuple(sorted((result.payload.get("updated_fields") or {}).keys())),
                raw_note_present=bool(result.payload.get("raw_note_present")),
                answer_text=kb_message.text,
            )
            return AssistantTurn(
                message=message.text,
                source="skill:dog_profile:enrich+knowledge_base",
                response_key=message.key,
                skill_results=tuple(ctx.skill_results),
                response_provenance="deterministic",
                skill_id=DOG_PROFILE_ENRICH_TOOL_ID,
            )

        message = build_enrich_confirmation(
            locale=ctx.locale,
            updated_fields=tuple(sorted((result.payload.get("updated_fields") or {}).keys())),
            raw_note_present=bool(result.payload.get("raw_note_present")),
        )
        return AssistantTurn(
            message=message.text,
            source="skill:dog_profile:enrich",
            response_key=message.key,
            skill_results=tuple(ctx.skill_results),
            response_provenance="deterministic",
            skill_id=DOG_PROFILE_ENRICH_TOOL_ID,
        )

    def assemble_open_intent_fallback(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        return None
