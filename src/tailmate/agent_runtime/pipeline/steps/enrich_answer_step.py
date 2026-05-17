"""EnrichAnswerStep — combined enrich + KB answer when message contains a question."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from tailmate.agent_runtime.pipeline.turn_context import TurnContext
from tailmate.agent_runtime.services.turn_messages import (
    build_enrich_and_answer_message,
    build_knowledge_base_answer,
    build_knowledge_base_out_of_scope,
)
from tailmate.contracts.constants import (
    DOG_PROFILE_ENRICH_TOOL_ID,
    KNOWLEDGE_BASE_RESULT_METADATA_KEY,
)


@dataclass
class EnrichAnswerStep:
    """Terminal step: combines enrich confirmation with a KB answer when applicable.

    Only fires when ``outcome == "enrich"`` **and** the message contains a
    question **and** the knowledge base returns a hit or out_of_scope result.
    Falls through to ``EnrichConfirmStep`` when any of those conditions fail.
    """

    step_id: ClassVar[str] = "enrich_answer"

    def run(self, ctx: TurnContext) -> None:
        if (
            ctx.intent is None
            or "knowledge_base" not in ctx.intent.matched_skills
            or ctx.dog_profile_result is None
            or ctx.dog_profile_result.outcome != "enrich"
        ):
            return

        knowledge_result = ctx.knowledge_result
        if knowledge_result is None or knowledge_result.status not in {"hit", "out_of_scope"}:
            return

        if knowledge_result.status == "hit":
            kb_message = build_knowledge_base_answer(
                locale=ctx.locale,
                answer=knowledge_result.answer,
                sources=knowledge_result.sources,
            )
        else:
            kb_message = build_knowledge_base_out_of_scope(locale=ctx.locale)

        ctx.response = build_enrich_and_answer_message(
            locale=ctx.locale,
            updated_fields=ctx.dog_profile_result.updated_fields,
            raw_note_present=ctx.dog_profile_result.raw_note_present,
            answer_text=kb_message.text,
        )
        ctx.skill_id = DOG_PROFILE_ENRICH_TOOL_ID
        ctx.source = "skill:dog_profile:enrich+knowledge_base"
        ctx.knowledge_result = knowledge_result
        ctx.session.attributes[KNOWLEDGE_BASE_RESULT_METADATA_KEY] = (
            knowledge_result.model_dump(mode="json")
        )
        ctx.is_terminal = True
