"""Runtime skill for strip-metadata routing."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.agent_runtime.pipeline.steps._tool_finder import find_tool
from tailmate.agent_runtime.pipeline.skill import IntentMatch
from tailmate.agent_runtime.pipeline.turn_context import AssistantTurn, SkillExecutionResult, TurnContext
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.services.turn_messages import (
    build_skill_error_message,
    build_strip_metadata_confirmation,
)
from tailmate.contracts.constants import STRIP_METADATA_TOOL_ID
from tailmate.contracts.constants import STRIP_METADATA_RESULT_METADATA_KEY
from tailmate.contracts.errors import TailmateError, SkillRegistrationError


@dataclass
class StripMetadataRuntimeSkill:
    """Owns strip-metadata routing decisions."""

    skill_registry: SkillRegistry
    observability: Observability | None = None
    skill_id: str = "strip_metadata"
    routing_description: str = ""
    depends_on: tuple[str, ...] = ()

    def classify(self, ctx: TurnContext) -> IntentMatch | None:
        if ctx.strip_request is None:
            return None
        return IntentMatch(intent="known", priority=100)

    def execute(self, ctx: TurnContext) -> SkillExecutionResult:
        if ctx.strip_request is None:
            return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

        tool = find_tool(self.skill_registry, STRIP_METADATA_TOOL_ID)
        if tool is None:
            raise SkillRegistrationError(
                "strip_metadata_request was provided but the strip_metadata tool is not registered."
            )

        try:
            result = tool.invoke(dict(ctx.strip_request))
            if self.observability is not None:
                self.observability.info(
                    "orchestrator_strip_metadata",
                    session_id=ctx.session_id,
                    logical_path=result["logical_path"],
                    media_kind=result["media_kind"],
                    locale=ctx.locale,
                )
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="success",
                payload=dict(result),
            )
        except TailmateError as exc:
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="error",
                payload={},
                error={"type": exc.error_type, "message": str(exc)},
            )
        except Exception as exc:
            return SkillExecutionResult(
                skill_id=self.skill_id,
                outcome="error",
                payload={},
                error={"type": type(exc).__name__, "message": "Unexpected internal failure."},
            )

    def apply_context(self, ctx: TurnContext, result: SkillExecutionResult) -> None:
        if result.outcome != "success":
            return
        ctx.session.attributes[STRIP_METADATA_RESULT_METADATA_KEY] = dict(result.payload)

    def assemble(
        self,
        ctx: TurnContext,
        result: SkillExecutionResult,
    ) -> AssistantTurn | None:
        if result.outcome == "success":
            message = build_strip_metadata_confirmation(
                locale=ctx.locale,
                resource_uri=str(result.payload["resource_uri"]),
            )
            return AssistantTurn(
                message=message.text,
                source="skill:strip_metadata",
                response_key=message.key,
                skill_results=tuple(ctx.skill_results),
                response_provenance="deterministic",
                skill_id=STRIP_METADATA_TOOL_ID,
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
