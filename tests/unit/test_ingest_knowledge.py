from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "ingest_knowledge.py"


def load_ingest_module():
    spec = importlib.util.spec_from_file_location("ingest_knowledge", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeEmbeddingClient:
    def __init__(self, embedding: list[float] | None = None) -> None:
        self.embedding = embedding or [0.1] * 768
        self.contents: list[str] = []

    def embed_text(self, text: str) -> list[float]:
        self.contents.append(text)
        return list(self.embedding)


class FakeCursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object]]] = []
        self.closed = False

    def execute(self, statement: str, params: list[object]) -> None:
        self.calls.append((statement, params))

    def close(self) -> None:
        self.closed = True


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.commits = 0
        self.closed = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.disposed = False

    def raw_connection(self) -> FakeConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


class FakeEngineFactory:
    def __init__(self, engine: FakeEngine) -> None:
        self.engine = engine

    def create(self) -> FakeEngine:
        return self.engine


def test_load_records_defaults_locale_and_parses_reviewed_at(tmp_path) -> None:
    ingest = load_ingest_module()
    input_path = tmp_path / "knowledge.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"id":"chunk-1","content":"Feed adult dogs twice daily.","source_label":"Feeding Guide"}',
                '{"id":"chunk-2","content":"Change water daily.","source_label":"Care Guide","locale":"vi","reviewed_at":"2026-03-28T10:00:00Z"}',
            ]
        ),
        encoding="utf-8",
    )

    records = ingest.load_records(input_path)

    assert [record.id for record in records] == ["chunk-1", "chunk-2"]
    assert records[0].locale == "en-AU"
    assert records[0].reviewed_at is None
    assert records[1].locale == "vi"
    assert records[1].reviewed_at.isoformat() == "2026-03-28T10:00:00+00:00"


def test_load_records_rejects_missing_required_fields(tmp_path) -> None:
    ingest = load_ingest_module()
    input_path = tmp_path / "knowledge.jsonl"
    input_path.write_text(
        '{"id":"chunk-1","content":"Feed adult dogs twice daily."}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source_label"):
        ingest.load_records(input_path)


def test_upsert_knowledge_chunks_embeds_and_upserts_records() -> None:
    ingest = load_ingest_module()
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    engine = FakeEngine(connection)
    engine_factory = FakeEngineFactory(engine)
    records = [
        ingest.KnowledgeChunkRecord(
            id="chunk-1",
            content="Feed adult dogs twice daily.",
            source_label="Feeding Guide",
            locale="en-AU",
        ),
        ingest.KnowledgeChunkRecord(
            id="chunk-2",
            content="Change water daily.",
            source_label="Care Guide",
            category="hydration",
            locale="vi",
        ),
    ]

    processed = ingest.upsert_knowledge_chunks(
        records=records,
        embedding_client=FakeEmbeddingClient(),
        engine_factory=engine_factory,
    )

    assert processed == 2
    assert connection.commits == 1
    assert engine.disposed is True
    assert cursor.closed is True
    assert "INSERT INTO knowledge_chunks" in cursor.calls[0][0]
    assert cursor.calls[0][1][:5] == [
        "chunk-1",
        "Feed adult dogs twice daily.",
        None,
        "Feeding Guide",
        "en-AU",
    ]
    assert cursor.calls[0][1][5].startswith("[0.1,0.1")


def test_upsert_knowledge_chunks_rejects_wrong_embedding_size() -> None:
    ingest = load_ingest_module()

    with pytest.raises(RuntimeError, match="768-dimensional"):
        ingest.upsert_knowledge_chunks(
            records=[
                ingest.KnowledgeChunkRecord(
                    id="chunk-1",
                    content="Feed adult dogs twice daily.",
                    source_label="Feeding Guide",
                )
            ],
            embedding_client=FakeEmbeddingClient([0.1, 0.2]),
            engine_factory=FakeEngineFactory(FakeEngine(FakeConnection(FakeCursor()))),
        )
