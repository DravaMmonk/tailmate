#!/usr/bin/env python3
"""Ingest reviewed knowledge chunks from JSONL into the direct PostgreSQL store."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tailmate.adapters.knowledge_base.retriever import (
    EMBEDDING_DIMENSIONS,
    VertexTextEmbeddingClient,
)
from tailmate.agent_runtime.services.turn_messages import DEFAULT_LOCALE
from tailmate.bootstrap.config import AppConfig
from tailmate.bootstrap.container import AppContainer


UPSERT_KNOWLEDGE_CHUNK_SQL = """
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


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def parse_reviewed_at(value: Any) -> datetime | None:
    """Parse optional reviewed timestamps from ISO-8601 values."""

    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def format_vector_literal(values: Sequence[float]) -> str:
    """Format an embedding into the pgvector literal representation."""

    return "[" + ",".join(f"{float(value):.12g}" for value in values) + "]"


class KnowledgeChunkRecord(BaseModel):
    """One reviewed JSONL record ready for embedding and persistence."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    category: str | None = None
    locale: str = Field(default=DEFAULT_LOCALE, min_length=1)
    reviewed_at: datetime | None = None

    @field_validator("id", "content", "source_label", "locale", mode="before")
    @classmethod
    def _validate_required_text(cls, value: Any, info) -> str:
        return _normalize_required_text(value, field_name=str(info.field_name))

    @field_validator("category", mode="before")
    @classmethod
    def _validate_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("reviewed_at", mode="before")
    @classmethod
    def _validate_reviewed_at(cls, value: Any) -> datetime | None:
        return parse_reviewed_at(value)


KnowledgeChunkRecord.model_rebuild()


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for JSONL ingestion."""

    parser = argparse.ArgumentParser(
        description="Ingest reviewed knowledge chunks into the direct PostgreSQL knowledge base.",
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="Path to the reviewed JSONL file.",
    )
    return parser


def load_records(path: Path) -> list[KnowledgeChunkRecord]:
    """Load and validate reviewed knowledge chunks from a JSONL file."""

    if not path.exists():
        raise FileNotFoundError(f"Knowledge JSONL file not found: {path}")
    records: list[KnowledgeChunkRecord] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number}.") from exc
        try:
            records.append(KnowledgeChunkRecord.model_validate(payload))
        except Exception as exc:
            raise ValueError(f"Invalid knowledge chunk on line {line_number}: {exc}") from exc
    if not records:
        raise ValueError("The JSONL file did not contain any knowledge chunks.")
    return records


def build_embedding_client(config: AppConfig, container: AppContainer) -> VertexTextEmbeddingClient:
    """Build the Vertex embedding client used by the ingest workflow."""

    api_key = container._get_actual_gemini_api_key()
    credentials = None if api_key else container._get_vertex_ai_credentials()
    if api_key is None and credentials is None:
        raise RuntimeError(
            "Vertex AI ADC or TAILMATE_GEMINI_API_KEY is required to ingest knowledge chunks."
        )
    return VertexTextEmbeddingClient(
        model_name=config.embedding_model,
        project_id=config.project_id,
        location=config.location,
        api_key=api_key,
        credentials=credentials,
    )


def upsert_knowledge_chunks(
    *,
    records: Iterable[KnowledgeChunkRecord],
    embedding_client,
    engine_factory,
) -> int:
    """Embed and upsert reviewed chunks into the direct knowledge store."""

    engine = engine_factory.create()
    connection = None
    cursor = None
    processed = 0
    try:
        connection = engine.raw_connection()
        cursor = connection.cursor()
        for record in records:
            embedding = embedding_client.embed_text(record.content)
            if len(embedding) != EMBEDDING_DIMENSIONS:
                raise RuntimeError(
                    "The configured embedding model did not return a 768-dimensional vector."
                )
            cursor.execute(
                UPSERT_KNOWLEDGE_CHUNK_SQL,
                [
                    record.id,
                    record.content,
                    record.category,
                    record.source_label,
                    record.locale,
                    format_vector_literal(embedding),
                    record.reviewed_at,
                ],
            )
            processed += 1
        connection.commit()
        return processed
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()
        engine.dispose()


def run_ingest(input_path: Path) -> int:
    """Run the ingest flow against the configured direct database."""

    config = AppConfig.from_env()
    if config.uses_db_gateway:
        raise RuntimeError("Knowledge ingestion only supports direct database mode.")
    container = AppContainer(config=config)
    records = load_records(input_path)
    processed = upsert_knowledge_chunks(
        records=records,
        embedding_client=build_embedding_client(config, container),
        engine_factory=container.build_engine_factory(),
    )
    print(json.dumps({"ingested": processed, "input_path": str(input_path)}, indent=2))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    args = build_parser().parse_args(argv)
    return run_ingest(args.input_path)


if __name__ == "__main__":
    raise SystemExit(main())
