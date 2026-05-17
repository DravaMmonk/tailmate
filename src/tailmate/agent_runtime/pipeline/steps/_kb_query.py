"""Shared knowledge-base query helper used by EnrichAnswerStep and KnowledgeBaseStep."""

from __future__ import annotations

from tailmate.agent_runtime.ports.knowledge_retriever import KnowledgeRetriever
from tailmate.agent_runtime.ports.observability import Observability
from tailmate.contracts.errors import TailmateError
from tailmate.contracts.knowledge import KnowledgeQueryInput, KnowledgeQueryOutput


def run_knowledge_base_query(
    *,
    knowledge_retriever: KnowledgeRetriever | None,
    observability: Observability,
    message: str,
    locale: str,
    session_id: str,
    dog_context: str | None = None,
) -> KnowledgeQueryOutput | None:
    """Query the knowledge base, returning ``None`` on error or when unavailable."""
    if knowledge_retriever is None:
        return None
    try:
        result = knowledge_retriever.query(
            KnowledgeQueryInput(user_message=message, locale=locale, dog_context=dog_context)
        )
        observability.info(
            "orchestrator_knowledge_base",
            session_id=session_id,
            status=result.status,
            confidence=result.confidence,
            source_count=len(result.sources),
            locale=locale,
        )
        return result
    except TailmateError as exc:
        observability.error(
            "orchestrator_knowledge_base_error",
            session_id=session_id,
            error_type=exc.error_type,
            error_message=str(exc),
        )
        return None
    except Exception as exc:
        observability.error(
            "orchestrator_knowledge_base_error",
            session_id=session_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return None
