from __future__ import annotations

import inspect

import pytest

from tailmate.adapters.knowledge_base.retriever import (
    GatewayKnowledgeRetriever,
    GeminiKnowledgeAnswerClient,
    PgVectorKnowledgeRetriever,
    VertexTextEmbeddingClient,
    _BaseKnowledgeRetriever,
)


def test_knowledge_base_retriever_base_is_abstract() -> None:
    assert inspect.isabstract(_BaseKnowledgeRetriever)

    with pytest.raises(TypeError, match="abstract class"):
        _BaseKnowledgeRetriever(embedding_client=object(), answer_client=object())  # type: ignore[arg-type]


def test_knowledge_base_retriever_concrete_classes_remain_instantiable() -> None:
    assert not inspect.isabstract(PgVectorKnowledgeRetriever)
    assert not inspect.isabstract(GatewayKnowledgeRetriever)


def test_knowledge_base_client_adapters_expose_required_methods() -> None:
    embedding_client = VertexTextEmbeddingClient(
        model_name="text-embedding-004",
        project_id="test-project",
        location="global",
    )
    answer_client = GeminiKnowledgeAnswerClient(
        model_name="gemini-2.5-flash",
        project_id="test-project",
        location="global",
    )

    assert callable(embedding_client.embed_text)
    assert callable(answer_client.generate_answer)
