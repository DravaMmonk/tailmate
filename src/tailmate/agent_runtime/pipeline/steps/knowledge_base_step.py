"""KnowledgeBaseStep — queries the knowledge base for noop turns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.turn_messages import (
    build_knowledge_base_answer,
    build_knowledge_base_out_of_scope,
)


@dataclass
class KnowledgeBaseStep:
    """Terminal step: answers questions from the knowledge base (noop path)."""

    step_id: ClassVar[str] = "knowledge_base"

    def run(self, ctx: TurnContext) -> None:
        if (
            ctx.intent is None
            or "knowledge_base" not in ctx.intent.matched_skills
            or ctx.dog_profile_result is None
            or ctx.dog_profile_result.outcome != "noop"
        ):
            return

        knowledge_result = ctx.knowledge_result
        ctx.knowledge_result = knowledge_result

        if knowledge_result is not None and knowledge_result.status == "hit":
            ctx.response = build_knowledge_base_answer(
                locale=ctx.locale,
                answer=knowledge_result.answer,
                sources=knowledge_result.sources,
            )
            ctx.source = "knowledge_base"
            ctx.is_terminal = True
        elif knowledge_result is not None and knowledge_result.status == "out_of_scope":
            ctx.response = build_knowledge_base_out_of_scope(locale=ctx.locale)
            ctx.source = "knowledge_base"
            ctx.is_terminal = True
