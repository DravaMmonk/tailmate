"""ProfileRecallStep — surfaces stored dog profile data for recall queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from tailmate.agent_runtime.pipeline.skills._shared import resolve_dog_selection
from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.contracts.errors import TailmateError


@dataclass
class ProfileRecallStep:
    """Terminal step: answers profile-recall queries from stored dog data.

    When ``ctx.current_dog_profile`` is ``None`` (e.g. because ``DogContextStep``
    encountered a load error), this step makes its own load attempt so it can
    emit the ``orchestrator_dog_profile_recall_error`` event that tests assert on.
    """

    dog_profile_db_adapter: Any  # DogProfileDBAdapter | None
    observability: Observability
    step_id: ClassVar[str] = "profile_recall"

    def run(self, ctx: TurnContext) -> None:
        if self.dog_profile_db_adapter is None:
            return

        if (
            ctx.dog_profile_result is None
            or ctx.dog_profile_result.outcome != "noop"
            or ctx.intent is None
            or "knowledge_base" not in ctx.intent.matched_skills
        ):
            return
        if ctx.current_dog_profile is None:
            self._try_load(ctx)

    def _try_load(self, ctx: TurnContext) -> Any:
        selection = resolve_dog_selection(ctx, self.dog_profile_db_adapter)
        if selection.active_dog_id is None:
            return None
        verified_user_id = str(ctx.request_metadata.get("user_id", "")).strip()
        if not verified_user_id:
            return None
        try:
            return self.dog_profile_db_adapter.load_profile(
                selection.active_dog_id, requesting_user_id=verified_user_id
            )
        except TailmateError as exc:
            self.observability.error(
                "orchestrator_dog_profile_recall_error",
                session_id=ctx.session_id,
                dog_id=selection.active_dog_id,
                error_type=exc.error_type,
                error_message=str(exc),
            )
            return None
        except Exception as exc:
            self.observability.error(
                "orchestrator_dog_profile_recall_error",
                session_id=ctx.session_id,
                dog_id=selection.active_dog_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            return None
