"""Runtime skill for dog-profile creation routing."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.adapters.dog_profile.extractors import detect_dog_name
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
    build_create_confirmation,
    build_skill_error_message,
)
from tailmate.contracts.constants import DOG_PROFILE_CREATE_TOOL_ID, DOG_PROFILE_RESULT_METADATA_KEY
from tailmate.contracts.errors import DomainError, TailmateError

from ._shared import has_tool, persist_active_dog, resolve_dog_selection


@dataclass
class DogProfileCreateRuntimeSkill:
    """Owns dog-profile create routing decisions."""

    skill_registry: SkillRegistry
    dog_profile_db_adapter: DogProfileDBAdapter | None = None
    observability: Observability | None = None
    skill_id: str = "dog_profile:create"
    routing_description: str = (
        "User introduces a dog by name for the first time and no active dog is already "
        "bound to the session."
    )
    depends_on: tuple[str, ...] = ()

    def classify(self, ctx: TurnContext) -> IntentMatch | None:
        if ctx.strip_request is not None:
            return None
        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        detected_name = detect_dog_name(ctx.message)
        if selection.active_dog_id is not None or detected_name is None:
            return None
        if not has_tool(self.skill_registry, DOG_PROFILE_CREATE_TOOL_ID):
            return None
        return IntentMatch(intent="known", priority=70)

    def execute(self, ctx: TurnContext) -> SkillExecutionResult:
        tool = find_tool(self.skill_registry, DOG_PROFILE_CREATE_TOOL_ID)
        if tool is None:
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        detected_name = detect_dog_name(ctx.message)
        if detected_name is None:
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        try:
            verified_user_id = str(ctx.request_metadata.get("user_id", "")).strip()
            if not verified_user_id:
                raise DomainError("Missing verified user_id in request metadata.")
            create_result = tool.invoke(
                {
                    "name": detected_name,
                    "session_id": ctx.session_id,
                    "user_id": verified_user_id,
                }
            )
            dog_id = str(create_result["dog_id"])
            if self.observability is not None:
                self.observability.info(
                    "orchestrator_dog_profile_create",
                    session_id=ctx.session_id,
                    dog_id=dog_id,
                    name=detected_name,
                )
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="create",
                payload={"created_name": detected_name, **dict(create_result)},
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
        if result.outcome == "create":
            persist_active_dog(ctx.session.attributes, str(result.payload["dog_id"]))
            ctx.session.attributes[DOG_PROFILE_RESULT_METADATA_KEY] = {
                "action": "create",
                "dog_id": result.payload["dog_id"],
                "profile_summary": result.payload["profile_summary"],
                "created_at": result.payload["created_at"],
            }
            ctx.dog_profile_result = DogProfileTurnResult(
                outcome="create",
                created_name=str(result.payload.get("created_name", "")) or None,
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
        if result.outcome == "create":
            created_name = str(result.payload.get("created_name", "")).strip()
            if not created_name:
                return None
            message = build_create_confirmation(locale=ctx.locale, name=created_name)
            return AssistantTurn(
                message=message.text,
                source="skill:dog_profile:create",
                response_key=message.key,
                skill_results=tuple(ctx.skill_results),
                response_provenance="deterministic",
                skill_id=DOG_PROFILE_CREATE_TOOL_ID,
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
