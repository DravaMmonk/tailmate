"""ResponseAssemblyStep — single-source response assembly from skill results."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.ports.conversational_responder import (
    ConversationalRequest,
    ConversationalResponder,
)
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.pipeline.turn_context import AssistantTurn, TurnContext
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.agent_runtime.services.safety_boundaries import classify_safety_boundary
from tailmate.agent_runtime.services.turn_messages import (
    build_fallback_message,
    build_llm_safety_redirect,
    classify_fallback_reason,
    localize_message,
    resolve_greeting_dog_name,
)


@dataclass
class ResponseAssemblyStep:
    """Assemble the assistant turn from structured skill results."""

    skill_registry: SkillRegistry
    conversational_responder: ConversationalResponder | None = None
    observability: Observability | None = None
    step_id: ClassVar[str] = "response_assembly"

    def run(self, ctx: TurnContext) -> None:
        assistant_turn = self._assemble_from_skill_results(ctx, include_errors=False)
        if assistant_turn is None:
            assistant_turn = self._assemble_from_skill_results(ctx, include_errors=True)
        if assistant_turn is not None:
            self._apply_assistant_turn(ctx, assistant_turn)
            return
        self._apply_assistant_turn(ctx, self._assemble_fallback(ctx))

    def _assemble_from_skill_results(
        self,
        ctx: TurnContext,
        *,
        include_errors: bool,
    ) -> AssistantTurn | None:
        for result in ctx.skill_results:
            if include_errors != (result.outcome == "error"):
                continue
            turn = self.skill_registry.get_skill(result.skill_id).assemble(ctx, result)
            if turn is not None:
                return turn
        return None

    def _assemble_fallback(self, ctx: TurnContext) -> AssistantTurn:
        if (
            ctx.intent is not None
            and ctx.intent.intent == "open"
            and self.conversational_responder is not None
        ):
            safety_redirect = self._assemble_safety_boundary_redirect(ctx)
            if safety_redirect is not None:
                return safety_redirect
        fallback_reason = classify_fallback_reason(
            ctx.message,
            ctx.locale,
            context_attributes=ctx.session.attributes,
            turns=ctx.session.turns,
        )
        if (
            ctx.intent is not None
            and ctx.intent.intent == "open"
            and fallback_reason == "fallback.no_skill_matched"
            and self.conversational_responder is not None
        ):
            llm_turn = self._assemble_conversational_fallback(ctx)
            if llm_turn is not None:
                return llm_turn
            deterministic_open_turn = self._assemble_open_intent_skill_fallback(ctx)
            if deterministic_open_turn is not None:
                return deterministic_open_turn
        return self._build_deterministic_fallback_turn(ctx, fallback_reason=fallback_reason)

    def can_stream_conversational_fallback(self, ctx: TurnContext) -> bool:
        """Return whether this turn can produce true incremental LLM output."""

        if ctx.intent is None or ctx.intent.intent != "open":
            return False
        if self.conversational_responder is None:
            return False
        if classify_safety_boundary(ctx.message).hit:
            return False
        fallback_reason = classify_fallback_reason(
            ctx.message,
            ctx.locale,
            context_attributes=ctx.session.attributes,
            turns=ctx.session.turns,
        )
        if fallback_reason != "fallback.no_skill_matched":
            return False
        return self._resolve_open_intent_scope(ctx) is not None

    def stream_conversational_fallback(self, ctx: TurnContext) -> Iterator[str]:
        """Yield true model deltas and return the final assistant turn."""

        system_scope = self._resolve_open_intent_scope(ctx)
        if system_scope is None or self.conversational_responder is None:
            deterministic_open_turn = self._assemble_open_intent_skill_fallback(ctx)
            return deterministic_open_turn or self._build_deterministic_fallback_turn(
                ctx,
                fallback_reason="fallback.no_skill_matched",
            )

        request = ConversationalRequest(
            user_message=ctx.message,
            locale=ctx.locale,
            dog_context=ctx.dog_context,
            recent_turns=tuple(ctx.session.turns[:-1][-6:]),
            system_scope=system_scope,
        )
        provenance = "llm_with_kb_scope" if system_scope == "kb_out_of_scope" else "llm_generated"
        disclaimer = localize_message("llm.unverified_disclaimer", ctx.locale).text
        streamed_chunks: list[str] = []

        try:
            for chunk in self.conversational_responder.stream_generate(request):
                if not chunk:
                    continue
                streamed_chunks.append(chunk)
                yield chunk
        except Exception as exc:
            if self.observability is not None:
                self.observability.error(
                    "orchestrator_conversational_fallback_error",
                    session_id=ctx.session_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            deterministic_open_turn = self._assemble_open_intent_skill_fallback(ctx)
            return deterministic_open_turn or self._build_deterministic_fallback_turn(
                ctx,
                fallback_reason="fallback.no_skill_matched",
            )

        if self.observability is not None:
            self.observability.info(
                "orchestrator_conversational_fallback",
                session_id=ctx.session_id,
                locale=ctx.locale,
                provenance=provenance,
                model=getattr(self.conversational_responder, "model_name", None),
                prompt_tokens=0,
                completion_tokens=0,
                has_dog_context=bool(ctx.dog_context),
                disclaimer_appended=True,
                streamed=True,
            )

        disclaimer_chunk = f"\n\n{disclaimer}"
        streamed_chunks.append(disclaimer_chunk)
        yield disclaimer_chunk
        return AssistantTurn(
            message="".join(streamed_chunks),
            source="llm:conversational",
            response_key="llm.generated",
            skill_results=tuple(ctx.skill_results),
            response_provenance=provenance,
            fallback_reason="fallback.no_skill_matched",
        )

    def _build_deterministic_fallback_turn(
        self,
        ctx: TurnContext,
        *,
        fallback_reason: str,
    ) -> AssistantTurn:
        dog_name = None
        if fallback_reason == "fallback.greeting":
            dog_name = resolve_greeting_dog_name(
                context_attributes=ctx.session.attributes,
                current_dog_profile=ctx.current_dog_profile,
                turns=ctx.session.turns[:-1],
            )
        message = build_fallback_message(
            locale=ctx.locale,
            reason=fallback_reason,
            dog_name=dog_name,
        )
        return AssistantTurn(
            message=message.text,
            source="fallback",
            response_key=message.key,
            skill_results=tuple(ctx.skill_results),
            response_provenance="deterministic",
            fallback_reason=fallback_reason,
        )

    def _assemble_conversational_fallback(self, ctx: TurnContext) -> AssistantTurn | None:
        system_scope = self._resolve_open_intent_scope(ctx)
        if system_scope is None:
            return None

        try:
            response = self.conversational_responder.generate(
                ConversationalRequest(
                    user_message=ctx.message,
                    locale=ctx.locale,
                    dog_context=ctx.dog_context,
                    recent_turns=tuple(ctx.session.turns[:-1][-6:]),
                    system_scope=system_scope,
                )
            )
        except Exception as exc:
            if self.observability is not None:
                self.observability.error(
                    "orchestrator_conversational_fallback_error",
                    session_id=ctx.session_id,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            return None
        return self._build_llm_conversational_turn(
            ctx,
            text=response.text,
            provenance=response.provenance,
            model=response.model,
            usage=response.usage,
        )

    def _assemble_safety_boundary_redirect(self, ctx: TurnContext) -> AssistantTurn | None:
        decision = classify_safety_boundary(ctx.message)
        if not decision.hit:
            return None
        ctx.safety_boundary_hit = True
        message = build_llm_safety_redirect(locale=ctx.locale)
        return AssistantTurn(
            message=message.text,
            source="fallback",
            response_key=message.key,
            skill_results=tuple(ctx.skill_results),
            response_provenance="deterministic",
            fallback_reason="fallback.no_skill_matched",
        )

    def _resolve_open_intent_scope(self, ctx: TurnContext) -> str | None:
        for result in ctx.skill_results:
            scope = result.payload.get("open_intent_scope")
            if scope == "error":
                return None
            if isinstance(scope, str) and scope:
                return scope
        return "kb_miss"

    def _assemble_open_intent_skill_fallback(self, ctx: TurnContext) -> AssistantTurn | None:
        for result in ctx.skill_results:
            fallback = result.payload.get("open_intent_fallback")
            if not isinstance(fallback, dict):
                turn = self.skill_registry.get_skill(result.skill_id).assemble_open_intent_fallback(
                    ctx,
                    result,
                )
                if turn is not None:
                    return turn
                continue
            return AssistantTurn(
                message=str(fallback["message"]),
                source=str(fallback["source"]),
                response_key=str(fallback["response_key"]),
                skill_results=tuple(ctx.skill_results),
                response_provenance=str(fallback["response_provenance"]),
            )
        return None

    def _build_llm_conversational_turn(
        self,
        ctx: TurnContext,
        *,
        text: str,
        provenance: str,
        model: str | None,
        usage: dict[str, int],
    ) -> AssistantTurn:
        disclaimer = localize_message("llm.unverified_disclaimer", ctx.locale).text
        if self.observability is not None:
            self.observability.info(
                "orchestrator_conversational_fallback",
                session_id=ctx.session_id,
                locale=ctx.locale,
                provenance=provenance,
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                has_dog_context=bool(ctx.dog_context),
                disclaimer_appended=True,
            )
        return AssistantTurn(
            message=f"{text}\n\n{disclaimer}",
            source="llm:conversational",
            response_key="llm.generated",
            skill_results=tuple(ctx.skill_results),
            response_provenance=provenance,
            fallback_reason="fallback.no_skill_matched",
        )

    @staticmethod
    def _apply_assistant_turn(ctx: TurnContext, assistant_turn: AssistantTurn) -> None:
        ctx.assistant_turn = assistant_turn
        ctx.skill_id = assistant_turn.skill_id
        ctx.source = assistant_turn.source
        ctx.fallback_reason = assistant_turn.fallback_reason
        ctx.response = type(
            "LocalizedTurnMessageProxy",
            (),
            {
                "text": assistant_turn.message,
                "key": assistant_turn.response_key,
            },
        )()
        ctx.is_terminal = True
