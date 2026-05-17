"""DogContextStep — resolves the active dog and prepares KB query context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from tailmate.adapters.dog_profile.extractors import detect_dog_name
from tailmate.agent_runtime.pipeline.skills._shared import persist_active_dog, resolve_dog_selection
from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.services.turn_messages import (
    format_dog_profile_context,
    is_referential_follow_up,
)
from tailmate.contracts.errors import TailmateError

_RECENT_TURN_WINDOW = 3
_RECENT_ASSISTANT_CONTEXT_LIMIT = 2


@dataclass
class DogContextStep:
    """Non-terminal step: loads current dog profile and enriches KB query context.

    Sets on ``ctx``:
    - ``current_dog_profile`` — the loaded ``DogProfile`` (or ``None`` on error/absence)
    - ``dog_context`` — formatted profile snapshot string for the KB prompt
    - ``knowledge_message`` — augmented message for referential follow-ups
    """

    dog_profile_db_adapter: Any  # DogProfileDBAdapter | None
    observability: Observability
    step_id: ClassVar[str] = "dog_context"

    def run(self, ctx: TurnContext) -> None:
        if ctx.intent is None:
            return

        matched_skills = set(ctx.intent.matched_skills)
        if "strip_metadata" in matched_skills or "dog_profile:create" in matched_skills:
            return

        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        if selection.active_dog_id is not None:
            persist_active_dog(ctx.session.attributes, selection.active_dog_id)
        if selection.active_profile is not None:
            ctx.current_dog_profile = selection.active_profile

        if (
            ctx.current_dog_profile is None
            and selection.active_dog_id is not None
            and self.dog_profile_db_adapter is not None
        ):
            verified_user_id = str(ctx.request_metadata.get("user_id", "")).strip()
            if verified_user_id:
                ctx.current_dog_profile = self._load_profile(
                    ctx, selection.active_dog_id, verified_user_id
                )

        if ctx.current_dog_profile is not None:
            ctx.dog_context = format_dog_profile_context(
                ctx.current_dog_profile, ctx.locale
            )

        # history-based dog_context fallback when profile is unavailable
        if ctx.dog_context is None:
            ctx.dog_context = self._history_dog_context(ctx)

        # augment the knowledge message for referential follow-ups
        augmented = self._augment_message(ctx)
        if augmented is not None:
            ctx.knowledge_message = augmented

    def _load_profile(
        self, ctx: TurnContext, dog_id: str, user_id: str
    ) -> Any:
        try:
            return self.dog_profile_db_adapter.load_profile(
                dog_id, requesting_user_id=user_id
            )
        except TailmateError as exc:
            self.observability.error(
                "orchestrator_dog_profile_context_error",
                session_id=ctx.session_id,
                dog_id=dog_id,
                error_type=exc.error_type,
                error_message=str(exc),
            )
            return None
        except Exception as exc:
            self.observability.error(
                "orchestrator_dog_profile_context_error",
                session_id=ctx.session_id,
                dog_id=dog_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return None

    @staticmethod
    def _history_dog_context(ctx: TurnContext) -> str | None:
        if not is_referential_follow_up(ctx.message, ctx.locale):
            return None
        recent = ctx.session.turns[:-1][-_RECENT_TURN_WINDOW:]
        for turn in reversed(recent):
            if str(turn.get("role", "")).strip() != "user":
                continue
            candidate = detect_dog_name(str(turn.get("message", "")))
            if candidate is not None:
                return f"Dog: {candidate}."
        return None

    @staticmethod
    def _augment_message(ctx: TurnContext) -> str | None:
        stripped = ctx.message.strip()
        if not is_referential_follow_up(stripped, ctx.locale):
            return None
        recent = ctx.session.turns[:-1][-_RECENT_TURN_WINDOW:]
        assistant_messages: list[str] = []
        for turn in reversed(recent):
            if str(turn.get("role", "")).strip() != "assistant":
                continue
            candidate = str(turn.get("message", "")).strip()
            if candidate:
                assistant_messages.append(candidate)
                if len(assistant_messages) >= _RECENT_ASSISTANT_CONTEXT_LIMIT:
                    break
        assistant_messages.reverse()
        if not assistant_messages:
            return None
        prior = " ".join(assistant_messages)
        return f"[Prior context: {prior}]\n\n{stripped}"
