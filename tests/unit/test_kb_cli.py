from __future__ import annotations

import argparse
import json

from tailmate.entrypoints import kb as kb_entrypoint


def test_run_kb_reindex_returns_error_when_gateway_mode_enabled(monkeypatch, capsys) -> None:
    class FakeConfig:
        uses_db_gateway = True

    class FakeContainer:
        config = FakeConfig()

    monkeypatch.setattr(kb_entrypoint, "build_local_container", lambda: FakeContainer())

    exit_code = kb_entrypoint.run_kb_reindex(argparse.Namespace())

    assert exit_code == 1
    assert "requires direct database mode" in capsys.readouterr().err


def test_run_kb_reindex_executes_reindex_workflow(monkeypatch, capsys) -> None:
    class FakeConfig:
        uses_db_gateway = False
        embedding_model = "text-embedding-004"
        project_id = "project-1"
        location = "us-central1"

    class FakeContainer:
        config = FakeConfig()

        def _get_actual_gemini_api_key(self):
            return "api-key"

        def _get_vertex_ai_credentials(self):
            return None

        def build_engine_factory(self):
            return "engine-factory"

    embedding_calls: list[dict[str, object]] = []
    reindex_calls: list[tuple[object, object]] = []
    monkeypatch.setattr(kb_entrypoint, "build_local_container", lambda: FakeContainer())
    monkeypatch.setattr(
        kb_entrypoint,
        "build_vertex_embedding_client",
        lambda **kwargs: embedding_calls.append(kwargs) or "embedding-client",
    )
    monkeypatch.setattr(
        kb_entrypoint,
        "reindex_knowledge_chunks",
        lambda engine_factory, *, embedding_client: reindex_calls.append(
            (engine_factory, embedding_client)
        )
        or {"reindexed": 3},
    )

    exit_code = kb_entrypoint.run_kb_reindex(argparse.Namespace())

    assert exit_code == 0
    assert embedding_calls == [
        {
            "model_name": "text-embedding-004",
            "project_id": "project-1",
            "location": "us-central1",
            "api_key": "api-key",
            "credentials": None,
        }
    ]
    assert reindex_calls == [("engine-factory", "embedding-client")]
    assert json.loads(capsys.readouterr().out) == {"reindexed": 3}
