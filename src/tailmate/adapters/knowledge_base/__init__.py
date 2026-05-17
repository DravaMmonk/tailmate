"""Knowledge base adapters."""

from tailmate.adapters.knowledge_base.retriever import (
    GatewayKnowledgeRetriever,
    GeminiKnowledgeAnswerClient,
    PgVectorKnowledgeRetriever,
    VertexTextEmbeddingClient,
)

__all__ = [
    "GatewayKnowledgeRetriever",
    "GeminiKnowledgeAnswerClient",
    "PgVectorKnowledgeRetriever",
    "VertexTextEmbeddingClient",
]
