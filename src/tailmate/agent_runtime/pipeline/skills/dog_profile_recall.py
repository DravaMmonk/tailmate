"""Runtime skill for dog-profile recall routing."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.agent_runtime.pipeline.skill import IntentMatch
from tailmate.agent_runtime.pipeline.turn_context import AssistantTurn, SkillExecutionResult, TurnContext
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.services.turn_messages import (
    build_dog_profile_recall_summary,
    build_skill_error_message,
)
from tailmate.contracts.constants import DOG_PROFILE_RESULT_METADATA_KEY
from tailmate.contracts.dog_profile import normalize_dog_profile
from tailmate.contracts.errors import TailmateError

from ._shared import is_recall_turn, persist_active_dog, resolve_dog_selection


@dataclass
class DogProfileRecallRuntimeSkill:
    """Owns dog-profile recall routing decisions."""

    dog_profile_db_adapter: DogProfileDBAdapter | None = None
    observability: Observability | None = None
    skill_id: str = "dog_profile:recall"
    routing_description: str = (
        "User asks to retrieve stored facts about the active dog, such as name, age, breed, "
        "weight, medical history, or a summary of known profile data."
    )
    depends_on: tuple[str, ...] = ()

    def classify(self, ctx: TurnContext) -> IntentMatch | None:
        if ctx.strip_request is not None:
            return None
        if not is_recall_turn(ctx, dog_profile_db_adapter=self.dog_profile_db_adapter):
            return None
        return IntentMatch(intent="known", priority=80)

    def execute(self, ctx: TurnContext) -> SkillExecutionResult:
        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        verified_user_id = str(ctx.request_metadata.get("user_id", "")).strip()
        if (
            self.dog_profile_db_adapter is None
            or selection.active_dog_id is None
            or not verified_user_id
        ):
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        try:
            profile = ctx.current_dog_profile or selection.active_profile
            if profile is None:
                profile = self.dog_profile_db_adapter.load_profile(
                    selection.active_dog_id,
                    requesting_user_id=verified_user_id,
                )
            if profile is None:
                return SkillExecutionResult(
                    skill_id=self.skill_id,
                    outcome="noop",
                    payload={},
                )
            if self.observability is not None:
                self.observability.info(
                    "orchestrator_dog_profile_recall",
                    session_id=ctx.session_id,
                    dog_id=selection.active_dog_id,
                    locale=ctx.locale,
                )
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="recall",
                payload={
                    "dog_id": selection.active_dog_id,
                    "profile": profile.model_dump(mode="json"),
                },
            )
        except TailmateError as exc:
            if self.observability is not None:
                self.observability.error(
                    "orchestrator_dog_profile_recall_error",
                    session_id=ctx.session_id,
                    dog_id=selection.active_dog_id,
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
                    "orchestrator_dog_profile_recall_error",
                    session_id=ctx.session_id,
                    dog_id=selection.active_dog_id,
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
        if result.outcome != "recall":
            return
        persist_active_dog(ctx.session.attributes, str(result.payload["dog_id"]))
        ctx.session.attributes[DOG_PROFILE_RESULT_METADATA_KEY] = {
            "action": "recall",
            "dog_id": result.payload["dog_id"],
            "profile": result.payload["profile"],
        }

    def assemble(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        if result.outcome == "recall":
            profile = normalize_dog_profile(result.payload.get("profile") or {})
            message = build_dog_profile_recall_summary(locale=ctx.locale, profile=profile)
            return AssistantTurn(
                message=message.text,
                source="memory:dog_profile",
                response_key=message.key,
                skill_results=tuple(ctx.skill_results),
                response_provenance="deterministic",
            )
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
        return None

    def assemble_open_intent_fallback(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        return None
