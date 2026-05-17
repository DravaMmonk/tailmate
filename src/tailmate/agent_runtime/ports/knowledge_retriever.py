"""Business port for verified knowledge retrieval."""

from __future__ import annotations

from typing import Protocol

from tailmate.contracts.knowledge import KnowledgeQueryInput, KnowledgeQueryOutput


class KnowledgeRetriever(Protocol):
    """Resolve a fallback question against the curated knowledge base."""

    def query(self, request: KnowledgeQueryInput) -> KnowledgeQueryOutput: ...
