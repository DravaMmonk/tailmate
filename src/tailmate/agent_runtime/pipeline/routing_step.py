"""RoutingStep protocol — the common interface for all pipeline steps."""

from __future__ import annotations

from typing import Protocol

from tailmate.agent_runtime.pipeline.turn_context import TurnContext


class RoutingStep(Protocol):
    """A single step in the turn routing pipeline.

    Each step inspects ``ctx``, optionally mutates it, and sets
    ``ctx.is_terminal = True`` when it produces a terminal response so the
    pipeline stops iterating.
    """

    step_id: str

    def run(self, ctx: TurnContext) -> None:
        """Execute this step against the current turn context."""
        ...
