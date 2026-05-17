"""Runtime skill for active-dog switching and multi-dog disambiguation."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.agent_runtime.pipeline.skill import IntentMatch
from tailmate.agent_runtime.pipeline.turn_context import AssistantTurn, SkillExecutionResult, TurnContext
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.services.turn_messages import (
    build_active_dog_selection_prompt,
    build_active_dog_switch_confirmation,
)

from ._shared import persist_active_dog, resolve_dog_selection


@dataclass
class DogProfileSwitchRuntimeSkill:
    """Owns active-dog switching and multi-dog selection prompts."""

    dog_profile_db_adapter: DogProfileDBAdapter | None = None
    observability: Observability | None = None
    skill_id: str = "dog_profile:switch"
    routing_description: str = (
        "User switches the active dog, references a different known dog by name, or needs to "
        "choose which known dog Tailmate should use before profile-specific help continues."
    )
    depends_on: tuple[str, ...] = ()

    def classify(self, ctx: TurnContext) -> IntentMatch | None:
        if ctx.strip_request is not None:
            return None

        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        if selection.needs_disambiguation:
            return IntentMatch(intent="known", priority=90)
        if selection.active_dog_id is None:
            return None
        if selection.explicit_switch:
            return IntentMatch(intent="known", priority=85)
        if (
            selection.matched_by_name
            and selection.current_active_dog_id is not None
            and selection.current_active_dog_id != selection.active_dog_id
        ):
            return IntentMatch(intent="known", priority=85)
        return None

    def execute(self, ctx: TurnContext) -> SkillExecutionResult:
        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)

        if selection.needs_disambiguation:
            dog_names = tuple(
                str(profile.name).strip()
                for profile in selection.available_profiles
                if str(profile.name).strip()
            )
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="select_required",
                payload={"dog_names": list(dog_names)},
            )

        if selection.active_dog_id is None:
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        if self.observability is not None and (
            selection.explicit_switch
            or (
                selection.current_active_dog_id is not None
                and selection.current_active_dog_id != selection.active_dog_id
            )
        ):
            self.observability.info(
                "orchestrator_active_dog_switch",
                session_id=ctx.session_id,
                previous_dog_id=selection.current_active_dog_id,
                active_dog_id=selection.active_dog_id,
                matched_by_name=selection.matched_by_name,
                explicit_switch=selection.explicit_switch,
            )

        return SkillExecutionResult(
            skill_id=self.skill_id,
            outcome="switched",
            payload={
                "dog_id": selection.active_dog_id,
                "dog_name": (
                    str(selection.active_profile.name).strip()
                    if selection.active_profile is not None
                    else ""
                ),
            },
        )

    def apply_context(self, ctx: TurnContext, result: SkillExecutionResult) -> None:
        if result.outcome != "switched":
            return
        dog_id = str(result.payload.get("dog_id", "")).strip()
        if dog_id:
            persist_active_dog(ctx.session.attributes, dog_id)

    def assemble(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        if self._has_other_actionable_result(ctx):
            return None
        if result.outcome == "select_required":
            dog_names = tuple(
                str(name).strip()
                for name in result.payload.get("dog_names") or []
                if str(name).strip()
            )
            if not dog_names:
                return None
            message = build_active_dog_selection_prompt(locale=ctx.locale, dog_names=dog_names)
            return AssistantTurn(
                message=message.text,
                source="memory:dog_profile_selection",
                response_key=message.key,
                skill_results=tuple(ctx.skill_results),
                response_provenance="deterministic",
                skill_id=self.skill_id,
            )
        if result.outcome != "switched":
            return None
        dog_name = str(result.payload.get("dog_name", "")).strip()
        if not dog_name:
            return None
        message = build_active_dog_switch_confirmation(locale=ctx.locale, name=dog_name)
        return AssistantTurn(
            message=message.text,
            source="memory:dog_profile_switch",
            response_key=message.key,
            skill_results=tuple(ctx.skill_results),
            response_provenance="deterministic",
            skill_id=self.skill_id,
        )

    def assemble_open_intent_fallback(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        return None

    def _has_other_actionable_result(self, ctx: TurnContext) -> bool:
        for result in ctx.skill_results:
            if result.skill_id == self.skill_id:
                continue
            if result.outcome not in {"noop", "error"}:
                return True
        return False
