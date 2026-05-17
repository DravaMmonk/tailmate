"""Knowledge base management helpers."""

from __future__ import annotations

from collections.abc import Iterable
import csv
import io
import json
from typing import Any
from uuid import uuid4

from google.auth.credentials import Credentials

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.knowledge_base.retriever import (
    EMBEDDING_DIMENSIONS,
    VertexTextEmbeddingClient,
)
from tailmate.agent_runtime.services.turn_messages import DEFAULT_LOCALE
from tailmate.contracts.errors import NotFoundError
from tailmate.contracts.knowledge import (
    KnowledgeChunkInput,
    KnowledgeChunkPreviewInput,
    KnowledgeSearchHit,
    normalize_knowledge_chunk_batch_input,
    normalize_knowledge_chunk_input,
    normalize_knowledge_search_hits,
)


INSERT_KNOWLEDGE_CHUNK_SQL = """
INSERT INTO knowledge_chunks (
    id,
    content,
    category,
    source_label,
    locale,
    embedding,
    reviewed_at
)
VALUES (%s, %s, %s, %s, %s, %s::vector, %s)
ON CONFLICT (id)
DO UPDATE SET
    content = EXCLUDED.content,
    category = EXCLUDED.category,
    source_label = EXCLUDED.source_label,
    locale = EXCLUDED.locale,
    embedding = EXCLUDED.embedding,
    reviewed_at = EXCLUDED.reviewed_at
"""

SELECT_KNOWLEDGE_CHUNK_SQL = """
SELECT
    id,
    content,
    category,
    source_label,
    locale,
    reviewed_at
FROM knowledge_chunks
WHERE id = %s
"""

DELETE_KNOWLEDGE_CHUNK_SQL = """
DELETE FROM knowledge_chunks
WHERE id = %s
RETURNING id
"""

SEARCH_KNOWLEDGE_CHUNK_SQL = """
SELECT
    content,
    source_label,
    category,
    locale,
    1 - (embedding <=> %s::vector) AS score
FROM knowledge_chunks
WHERE locale = %s
ORDER BY embedding <=> %s::vector
LIMIT %s
"""

SELECT_ALL_KNOWLEDGE_CHUNKS_SQL = """
SELECT
    id,
    content
FROM knowledge_chunks
ORDER BY created_at, id
"""

UPDATE_KNOWLEDGE_CHUNK_EMBEDDING_SQL = """
UPDATE knowledge_chunks
SET embedding = %s::vector
WHERE id = %s
"""


def format_vector_literal(values: Iterable[float]) -> str:
    """Format a vector for pgvector-compatible SQL parameters."""

    return "[" + ",".join(f"{float(value):.12g}" for value in values) + "]"


def build_vertex_embedding_client(
    *,
    model_name: str,
    project_id: str,
    location: str,
    api_key: str | None = None,
    credentials: Credentials | None = None,
) -> VertexTextEmbeddingClient:
    """Build the Vertex embedding client used by management and ingest workflows."""

    return VertexTextEmbeddingClient(
        model_name=model_name,
        project_id=project_id,
        location=location,
        api_key=api_key,
        credentials=credentials,
    )


def _normalize_content_type(content_type: str | None) -> str:
    return (content_type or "").split(";", maxsplit=1)[0].strip().lower()


def load_knowledge_chunk_upload_records(
    raw_bytes: bytes,
    *,
    content_type: str | None,
    filename: str | None = None,
) -> list[KnowledgeChunkInput]:
    """Parse a CSV or JSON upload into normalized chunk records."""

    normalized_content_type = _normalize_content_type(content_type)
    normalized_filename = (filename or "").strip().lower()
    if "csv" in normalized_content_type or normalized_filename.endswith(".csv"):
        text = raw_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(row) for row in reader]
        if not rows:
            raise ValueError("The CSV upload did not contain any knowledge chunks.")
        return [normalize_knowledge_chunk_input(row) for row in rows]

    if "json" in normalized_content_type or normalized_filename.endswith(".json"):
        payload = json.loads(raw_bytes.decode("utf-8"))
        return normalize_knowledge_chunk_batch_input(payload).chunks

    raise ValueError("Upload content must be CSV or JSON.")


def _serialize_chunk_row(row: tuple[object, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "content": row[1],
        "category": row[2],
        "source_label": row[3],
        "locale": row[4],
        "reviewed_at": row[5].isoformat() if row[5] is not None else None,
    }


def create_knowledge_chunk(
    engine_factory: DatabaseEngineFactory,
    *,
    payload: KnowledgeChunkInput,
    embedding_client: VertexTextEmbeddingClient,
) -> dict[str, Any]:
    """Embed and persist one reviewed knowledge chunk."""

    chunk_id = payload.id or str(uuid4())
    embedding = embedding_client.embed_text(payload.content)
    if len(embedding) != EMBEDDING_DIMENSIONS:
        raise RuntimeError("The configured embedding model did not return a 768-dimensional vector.")
    engine = engine_factory.create()
    connection = None
    cursor = None
    try:
        connection = engine.raw_connection()
        cursor = connection.cursor()
        cursor.execute(
            INSERT_KNOWLEDGE_CHUNK_SQL,
            [
                chunk_id,
                payload.content,
                payload.category,
                payload.source_label,
                payload.locale,
                format_vector_literal(embedding),
                payload.reviewed_at,
            ],
        )
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
        engine.dispose()
    return {
        "chunk": {
            **payload.model_dump(mode="json"),
            "id": chunk_id,
        },
        "embedding_dimensions": len(embedding),
    }


def delete_knowledge_chunk(
    engine_factory: DatabaseEngineFactory,
    *,
    chunk_id: str,
) -> dict[str, Any]:
    """Delete one knowledge chunk by id."""

    engine = engine_factory.create()
    connection = None
    cursor = None
    try:
        connection = engine.raw_connection()
        cursor = connection.cursor()
        cursor.execute(DELETE_KNOWLEDGE_CHUNK_SQL, [chunk_id])
        row = cursor.fetchone()
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
        engine.dispose()
    if row is None:
        raise NotFoundError(f"Knowledge chunk '{chunk_id}' was not found.")
    return {"deleted": True, "chunk_id": str(row[0])}


def preview_knowledge_chunks(
    engine_factory: DatabaseEngineFactory,
    *,
    payload: KnowledgeChunkPreviewInput,
    embedding_client: VertexTextEmbeddingClient,
) -> list[KnowledgeSearchHit]:
    """Return similarity hits for an internal KB preview query."""

    embedding = embedding_client.embed_text(payload.query)
    hits = search_knowledge_chunks(
        engine_factory,
        embedding=embedding,
        locale=payload.locale,
        top_k=payload.top_k,
    )
    if not hits and payload.locale != DEFAULT_LOCALE:
        hits = search_knowledge_chunks(
            engine_factory,
            embedding=embedding,
            locale=DEFAULT_LOCALE,
            top_k=payload.top_k,
        )
    return hits


def search_knowledge_chunks(
    engine_factory: DatabaseEngineFactory,
    *,
    embedding: list[float],
    locale: str,
    top_k: int,
) -> list[KnowledgeSearchHit]:
    """Search the reviewed knowledge corpus by embedding similarity."""

    vector_literal = format_vector_literal(embedding)
    engine = engine_factory.create()
    connection = None
    cursor = None
    try:
        connection = engine.raw_connection()
        cursor = connection.cursor()
        cursor.execute(
            SEARCH_KNOWLEDGE_CHUNK_SQL,
            [vector_literal, locale, vector_literal, top_k],
        )
        rows = cursor.fetchall()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
        engine.dispose()
    return normalize_knowledge_search_hits(
        [
            {
                "content": row[0],
                "source_label": row[1],
                "category": row[2],
                "locale": row[3],
                "score": float(row[4]),
            }
            for row in rows
        ]
    )


def import_knowledge_chunks(
    engine_factory: DatabaseEngineFactory,
    *,
    records: Iterable[KnowledgeChunkInput],
    embedding_client: VertexTextEmbeddingClient,
) -> dict[str, Any]:
    """Embed and persist a batch of reviewed knowledge chunks."""

    imported_chunks: list[dict[str, Any]] = []
    engine = engine_factory.create()
    connection = None
    cursor = None
    try:
        connection = engine.raw_connection()
        cursor = connection.cursor()
        for record in records:
            chunk_id = record.id or str(uuid4())
            embedding = embedding_client.embed_text(record.content)
            if len(embedding) != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    "The configured embedding model did not return a 768-dimensional vector."
                )
            cursor.execute(
                INSERT_KNOWLEDGE_CHUNK_SQL,
                [
                    chunk_id,
                    record.content,
                    record.category,
                    record.source_label,
                    record.locale,
                    format_vector_literal(embedding),
                    record.reviewed_at,
                ],
            )
            imported_chunks.append(
                {
                    **record.model_dump(mode="json"),
                    "id": chunk_id,
                }
            )
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
        engine.dispose()
    return {
        "imported": len(imported_chunks),
        "chunk_ids": [chunk["id"] for chunk in imported_chunks],
        "chunks": imported_chunks,
    }


def reindex_knowledge_chunks(
    engine_factory: DatabaseEngineFactory,
    *,
    embedding_client: VertexTextEmbeddingClient,
) -> dict[str, Any]:
    """Rebuild embeddings for all reviewed knowledge chunks."""

    engine = engine_factory.create()
    connection = None
    cursor = None
    try:
        connection = engine.raw_connection()
        cursor = connection.cursor()
        cursor.execute(SELECT_ALL_KNOWLEDGE_CHUNKS_SQL)
        rows = cursor.fetchall()
        processed = 0
        for chunk_id, content in rows:
            embedding = embedding_client.embed_text(str(content))
            if len(embedding) != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    "The configured embedding model did not return a 768-dimensional vector."
                )
            cursor.execute(
                UPDATE_KNOWLEDGE_CHUNK_EMBEDDING_SQL,
                [format_vector_literal(embedding), chunk_id],
            )
            processed += 1
        connection.commit()
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
        engine.dispose()
    return {"reindexed": processed}
