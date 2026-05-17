from __future__ import annotations

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory


def test_engine_factory_passes_connect_args(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_engine(database_url: str, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(
        "tailmate.adapters.database.engine_factory.create_engine",
        fake_create_engine,
    )

    factory = DatabaseEngineFactory(
        "postgresql+psycopg2://user:pw@10.0.0.10:5432/postgres",
        connect_args={"connect_timeout": 10, "application_name": "tailmate_root"},
    )

    factory.create()

    assert captured == {
        "database_url": "postgresql+psycopg2://user:pw@10.0.0.10:5432/postgres",
        "kwargs": {
            "pool_pre_ping": True,
            "connect_args": {
                "connect_timeout": 10,
                "application_name": "tailmate_root",
            },
        },
    }
