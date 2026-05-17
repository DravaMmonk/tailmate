"""DogProfileStep — runs dog-profile create/enrich; sets ctx.dog_profile_result."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from tailmate.adapters.dog_profile.extractors import detect_dog_name
from tailmate.agent_runtime.pipeline.steps._tool_finder import find_tool
from tailmate.agent_runtime.pipeline.turn_context import DogProfileTurnResult, TurnContext
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.contracts.constants import (
    DOG_PROFILE_CREATE_TOOL_ID,
    DOG_PROFILE_ENRICH_TOOL_ID,
    DOG_PROFILE_RESULT_METADATA_KEY,
)
from tailmate.contracts.errors import DomainError, TailmateError


def _resolve_active_dog_id(
    context: Any,
    request_metadata: dict[str, Any],
) -> str | None:
    for candidate in (request_metadata.get("dog_id"), context.attributes.get("dog_id")):
        if candidate is None:
            continue
        normalized = str(candidate).strip()
        if normalized:
            return normalized
    return None


@dataclass
class DogProfileStep:
    """Non-terminal step: attempts create/enrich and populates ctx.dog_profile_result."""

    skill_registry: SkillRegistry
    observability: Observability
    step_id: ClassVar[str] = "dog_profile"

    def run(self, ctx: TurnContext) -> None:
        result = self._run_dog_profile(ctx)
        ctx.dog_profile_result = result
        ctx.skill_attempted = list(result.attempted_tools)
        ctx.skill_error = result.skill_error
        ctx.updated_fields = list(result.updated_fields)
        ctx.raw_note_saved = result.raw_note_present

    def _run_dog_profile(self, ctx: TurnContext) -> DogProfileTurnResult:
        if ctx.intent is None:
            return DogProfileTurnResult(outcome="noop")

        should_create = "dog_profile:create" in ctx.intent.matched_skills
        should_enrich = "dog_profile:enrich" in ctx.intent.matched_skills
        if not should_create and not should_enrich:
            return DogProfileTurnResult(outcome="noop")

        create_tool = find_tool(self.skill_registry, DOG_PROFILE_CREATE_TOOL_ID)
        enrich_tool = find_tool(self.skill_registry, DOG_PROFILE_ENRICH_TOOL_ID)
        if should_create and create_tool is None:
            return DogProfileTurnResult(outcome="noop")
        if should_enrich and enrich_tool is None:
            return DogProfileTurnResult(outcome="noop")

        verified_user_id = str(ctx.request_metadata.get("user_id", "")).strip()
        active_dog_id = _resolve_active_dog_id(ctx.session, ctx.request_metadata)
        attempted_tools: list[str] = []

        try:
            if should_create:
                detected_name = detect_dog_name(ctx.message)
                if detected_name is None:
                    return DogProfileTurnResult(outcome="noop")
                if not verified_user_id:
                    raise DomainError("Missing verified user_id in request metadata.")
                attempted_tools.append(DOG_PROFILE_CREATE_TOOL_ID)
                create_result = create_tool.invoke(
                    {
                        "name": detected_name,
                        "session_id": ctx.session_id,
                        "user_id": verified_user_id,
                    }
                )
                active_dog_id = str(create_result["dog_id"])
                ctx.session.attributes["dog_id"] = active_dog_id
                ctx.session.attributes[DOG_PROFILE_RESULT_METADATA_KEY] = {
                    "action": "create",
                    **create_result,
                }
                self.observability.info(
                    "orchestrator_dog_profile_create",
                    session_id=ctx.session_id,
                    dog_id=active_dog_id,
                    name=detected_name,
                )
                return DogProfileTurnResult(
                    outcome="create",
                    created_name=detected_name,
                    attempted_tools=tuple(attempted_tools),
                )

            if not should_enrich or active_dog_id is None:
                return DogProfileTurnResult(
                    outcome="noop",
                    attempted_tools=tuple(attempted_tools),
                )

            ctx.session.attributes["dog_id"] = active_dog_id
            attempted_tools.append(DOG_PROFILE_ENRICH_TOOL_ID)
            if not verified_user_id:
                raise DomainError("Missing verified user_id in request metadata.")
            enrich_result = enrich_tool.invoke(
                {
                    "dog_id": active_dog_id,
                    "requesting_user_id": verified_user_id,
                    "user_message": ctx.message,
                }
            )
            has_updates = bool(enrich_result.get("updated_fields")) or bool(
                enrich_result.get("raw_note")
            )
            if has_updates:
                ctx.session.attributes[DOG_PROFILE_RESULT_METADATA_KEY] = {
                    "action": "enrich",
                    "dog_id": active_dog_id,
                    **enrich_result,
                }
                self.observability.info(
                    "orchestrator_dog_profile_enrich",
                    session_id=ctx.session_id,
                    dog_id=active_dog_id,
                    updated_fields=sorted((enrich_result.get("updated_fields") or {}).keys()),
                    strategy=enrich_result.get("extraction_strategy_used"),
                )
                return DogProfileTurnResult(
                    outcome="enrich",
                    updated_fields=tuple(
                        sorted((enrich_result.get("updated_fields") or {}).keys())
                    ),
                    raw_note_present=bool(enrich_result.get("raw_note")),
                    attempted_tools=tuple(attempted_tools),
                )
            return DogProfileTurnResult(
                outcome="noop",
                attempted_tools=tuple(attempted_tools),
            )
        except TailmateError as exc:
            self.observability.error(
                "orchestrator_dog_profile_error",
                session_id=ctx.session_id,
                error_type=exc.error_type,
                error_message=str(exc),
            )
            return DogProfileTurnResult(
                outcome="error",
                attempted_tools=tuple(attempted_tools),
                skill_error={"type": exc.error_type, "message": str(exc)},
            )
        except Exception as exc:
            self.observability.error(
                "orchestrator_dog_profile_error",
                session_id=ctx.session_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return DogProfileTurnResult(
                outcome="error",
                attempted_tools=tuple(attempted_tools),
                skill_error={
                    "type": type(exc).__name__,
                    "message": "Unexpected internal failure.",
                },
            )
