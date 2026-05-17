"""SkillExecutionStep — executes matched skills and records structured results."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import DogProfileTurnResult, SkillExecutionResult, TurnContext
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.agent_runtime.ports.skill_registry import SkillRegistry
from tailmate.metrics import record_skill_invocation


@dataclass
class SkillExecutionStep:
    """Execute the matched skill list before response assembly begins."""

    skill_registry: SkillRegistry
    observability: Observability
    dog_profile_db_adapter: object | None
    knowledge_retriever: object | None
    step_id: ClassVar[str] = "skill_execution"

    def run(self, ctx: TurnContext) -> None:
        ctx.execution_phase_started_at = time.monotonic()
        ctx.skill_results = []
        ctx.dog_profile_result = DogProfileTurnResult(outcome="noop")
        ctx.knowledge_result = None
        ctx.skill_attempted = []
        ctx.skill_error = None
        ctx.updated_fields = []
        ctx.raw_note_saved = False

        if ctx.intent is None:
            return

        levels = self._topological_levels(ctx.intent.matched_skills)
        if any(len(level) > 1 for level in levels):
            self.observability.info(
                "orchestrator_turn_parallel_skills",
                session_id=ctx.session_id,
                skill_ids=list(ctx.intent.matched_skills),
                level_count=len(levels),
            )

        for level in levels:
            level_results = self._execute_level(ctx, level)
            for result in level_results:
                ctx.skill_results.append(result)
                ctx.skill_attempted.append(result.skill_id)
                record_skill_invocation(skill=result.skill_id, status=result.outcome)
                self.observability.info(
                    "orchestrator_skill_executed",
                    session_id=ctx.session_id,
                    skill_id=result.skill_id,
                    outcome=result.outcome,
                    duration_ms=result.duration_ms,
                )
                self._apply_result_to_context(ctx, result)

    def _execute_level(self, ctx: TurnContext, level: tuple[str, ...]) -> list[SkillExecutionResult]:
        if len(level) <= 1:
            return [self._execute_skill(ctx, level[0])] if level else []

        with ThreadPoolExecutor(max_workers=len(level)) as executor:
            futures = {
                skill_id: executor.submit(self._execute_skill, ctx, skill_id)
                for skill_id in level
            }
            return [futures[skill_id].result() for skill_id in level]

    def _topological_levels(self, matched_skills: tuple[str, ...]) -> list[tuple[str, ...]]:
        remaining = list(matched_skills)
        resolved: set[str] = set()
        levels: list[tuple[str, ...]] = []

        while remaining:
            level = tuple(
                skill_id
                for skill_id in remaining
                if set(self._dependencies_for(skill_id, matched_skills)).issubset(resolved)
            )
            if not level:
                level = tuple(remaining)
            levels.append(level)
            resolved.update(level)
            remaining = [skill_id for skill_id in remaining if skill_id not in resolved]

        return levels

    def _dependencies_for(self, skill_id: str, matched_skills: tuple[str, ...]) -> tuple[str, ...]:
        skill = self.skill_registry.get_skill(skill_id)
        return tuple(dep for dep in skill.depends_on if dep in matched_skills)

    def _execute_skill(self, ctx: TurnContext, skill_id: str) -> SkillExecutionResult:
        started_at = time.monotonic()
        result = self.skill_registry.get_skill(skill_id).execute(ctx)
        duration_ms = int((time.monotonic() - started_at) * 1000)
        return replace(result, duration_ms=duration_ms)

    def _apply_result_to_context(self, ctx: TurnContext, result: SkillExecutionResult) -> None:
        skill = self.skill_registry.get_skill(result.skill_id)
        apply_context = getattr(skill, "apply_context", None)
        if apply_context is None:
            return
        apply_context(ctx, result)
