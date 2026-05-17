from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.bootstrap.config import AppConfig


def build_local_config(tmp_path: Path, *, extraction_strategy: str = "composite") -> AppConfig:
    return AppConfig.model_validate(
        {
            "TAILMATE_PROJECT_ID": "test-project",
            "TAILMATE_LOCATION": "us-central1",
            "TAILMATE_ENV": "LOCAL",
            "TAILMATE_DB_USER": "user",
            "TAILMATE_DB_PASSWORD": "pass",
            "TAILMATE_DB_IP": "10.0.0.10",
            "TAILMATE_DB_NAME": "postgres",
            "TAILMATE_LOCAL_TUNNEL_HOST": "127.0.0.1",
            "TAILMATE_LOCAL_TUNNEL_PORT": 5432,
            "TAILMATE_EXTRACTION_STRATEGY": extraction_strategy,
        }
    )


def test_check_environment_requires_env_file(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module("tailmate.entrypoints.local_dev")

    config = build_local_config(tmp_path)

    with pytest.raises(RuntimeError, match="requires a \\.env file"):
        module.check_environment(config)


def test_check_environment_validates_tunnel_and_adc_for_flash_strategy(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    module = importlib.import_module("tailmate.entrypoints.local_dev")
    env_module = importlib.import_module("tailmate.entrypoints.local_env")

    entered = False

    class FakeSocket:
        def __enter__(self):
            nonlocal entered
            entered = True
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeCredentials:
        def __init__(self) -> None:
            self.refreshed = False

        def refresh(self, request) -> None:
            self.refreshed = isinstance(request, env_module.Request)

    credentials = FakeCredentials()
    monkeypatch.setattr(env_module.socket, "create_connection", lambda address, timeout: FakeSocket())
    monkeypatch.setattr(
        env_module.google.auth,
        "default",
        lambda scopes: (credentials, "test-project"),
    )
    sync_calls: list[AppConfig] = []
    monkeypatch.setattr(
        env_module,
        "sync_local_database_schema",
        lambda config: sync_calls.append(config) or "Local test database schema synced.",
    )

    module.check_environment(build_local_config(tmp_path, extraction_strategy="flash"))

    assert entered
    assert len(sync_calls) == 1
    assert credentials.refreshed


def test_check_environment_allows_rule_strategy_without_adc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    module = importlib.import_module("tailmate.entrypoints.local_dev")
    env_module = importlib.import_module("tailmate.entrypoints.local_env")

    entered = False

    class FakeSocket:
        def __enter__(self):
            nonlocal entered
            entered = True
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(env_module.socket, "create_connection", lambda address, timeout: FakeSocket())
    monkeypatch.setattr(
        env_module.google.auth,
        "default",
        lambda scopes: pytest.fail("ADC should not be validated for rule extraction."),
    )
    sync_calls: list[AppConfig] = []
    monkeypatch.setattr(
        env_module,
        "sync_local_database_schema",
        lambda config: sync_calls.append(config) or "Local test database schema synced.",
    )

    module.check_environment(build_local_config(tmp_path, extraction_strategy="rule"))

    assert entered
    assert len(sync_calls) == 1


def test_check_environment_allows_composite_strategy_without_adc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    module = importlib.import_module("tailmate.entrypoints.local_dev")
    env_module = importlib.import_module("tailmate.entrypoints.local_env")

    entered = False

    class FakeSocket:
        def __enter__(self):
            nonlocal entered
            entered = True
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(env_module.socket, "create_connection", lambda address, timeout: FakeSocket())
    monkeypatch.setattr(
        env_module.google.auth,
        "default",
        lambda scopes: pytest.fail("ADC should stay optional for composite extraction."),
    )
    sync_calls: list[AppConfig] = []
    monkeypatch.setattr(
        env_module,
        "sync_local_database_schema",
        lambda config: sync_calls.append(config) or "Local test database schema synced.",
    )

    module.check_environment(build_local_config(tmp_path, extraction_strategy="composite"))

    assert entered
    assert len(sync_calls) == 1


def test_check_environment_requires_adc_for_flash_strategy(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    module = importlib.import_module("tailmate.entrypoints.local_dev")
    env_module = importlib.import_module("tailmate.entrypoints.local_env")

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def raise_missing_adc(*, scopes):
        raise env_module.DefaultCredentialsError("missing adc")

    monkeypatch.setattr(env_module.socket, "create_connection", lambda address, timeout: FakeSocket())
    monkeypatch.setattr(env_module.google.auth, "default", raise_missing_adc)
    monkeypatch.setattr(
        env_module,
        "sync_local_database_schema",
        lambda config: "Local test database schema synced.",
    )

    with pytest.raises(RuntimeError, match="requires Vertex AI ADC"):
        module.check_environment(build_local_config(tmp_path, extraction_strategy="flash"))


def test_check_environment_requires_explicit_local_env_marker(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_PROJECT_ID=test-project\n", encoding="utf-8")
    module = importlib.import_module("tailmate.entrypoints.local_dev")

    with pytest.raises(RuntimeError, match="TAILMATE_ENV=LOCAL explicitly"):
        module.check_environment(build_local_config(tmp_path))


def test_sync_local_database_schema_forces_alembic_to_use_local_database_url(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    monkeypatch.setenv("TAILMATE_ALEMBIC_DATABASE_URL", "postgresql://external-db")
    module = importlib.import_module("tailmate.entrypoints.local_env")

    config = build_local_config(tmp_path)
    monkeypatch.setattr(module, "build_alembic_config", lambda: object())

    class FakeScriptDirectory:
        def get_heads(self) -> tuple[str, ...]:
            return ("head-1",)

    monkeypatch.setattr(
        module.ScriptDirectory,
        "from_config",
        lambda _config: FakeScriptDirectory(),
    )
    monkeypatch.setattr(module, "_load_current_schema_heads", lambda _config: ())

    reset_calls: list[AppConfig] = []
    monkeypatch.setattr(
        module,
        "reset_local_database_schema",
        lambda sync_config: reset_calls.append(sync_config),
    )

    class FakeContainer:
        def __init__(self, config: AppConfig) -> None:
            self.config = config

        def build_database_url(self) -> str:
            return "postgresql://local-test-db"

    monkeypatch.setitem(sys.modules, "tailmate.bootstrap.container", SimpleNamespace(AppContainer=FakeContainer))

    seen_urls: list[str] = []

    def fake_upgrade(_config, target: str) -> None:
        assert target == "heads"
        seen_urls.append(os.environ["TAILMATE_ALEMBIC_DATABASE_URL"])

    monkeypatch.setattr(module.command, "upgrade", fake_upgrade)

    message = module.sync_local_database_schema(config)

    assert len(reset_calls) == 1
    assert seen_urls == ["postgresql://local-test-db"]
    assert os.environ["TAILMATE_ALEMBIC_DATABASE_URL"] == "postgresql://external-db"
    assert message == "Local test database schema was reset and synchronized to the current migration heads."


def test_ensure_local_user_exists_supports_legacy_users_schema(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    module = importlib.import_module("tailmate.entrypoints.local_env")

    class FakeResult:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return iter(self._values)

    class FakeConnection:
        def __init__(self) -> None:
            self.executed: list[tuple[str, dict[str, object] | None]] = []
            self.column_results = [
                {"user_id", "status", "role", "created_at"},
                set(),
            ]

        def execute(self, statement, params=None):
            sql = str(statement)
            self.executed.append((sql, params))
            if "information_schema.columns" in sql:
                return FakeResult(self.column_results.pop(0))
            return FakeResult([])

    class FakeBegin:
        def __init__(self, connection: FakeConnection) -> None:
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def __init__(self) -> None:
            self.connection = FakeConnection()
            self.disposed = False

        def begin(self):
            return FakeBegin(self.connection)

        def dispose(self) -> None:
            self.disposed = True

    fake_engine = FakeEngine()

    class FakeContainer:
        def __init__(self, config: AppConfig) -> None:
            self.config = config

        def build_engine_factory(self):
            return SimpleNamespace(create=lambda: fake_engine)

    monkeypatch.setitem(sys.modules, "tailmate.bootstrap.container", SimpleNamespace(AppContainer=FakeContainer))

    module.ensure_local_user_exists(build_local_config(tmp_path), "user-1")

    insert_statements = [sql for sql, _ in fake_engine.connection.executed if "INSERT INTO users" in sql]
    assert len(insert_statements) == 1
    _, params = next(
        (sql, params)
        for sql, params in fake_engine.connection.executed
        if "INSERT INTO users" in sql
    )
    assert params == {"user_id": "user-1", "status": "active", "role": "owner"}
    assert fake_engine.disposed is True


def test_ensure_local_user_exists_supports_split_user_schema(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    module = importlib.import_module("tailmate.entrypoints.local_env")

    class FakeResult:
        def __init__(self, values):
            self._values = values

        def scalars(self):
            return iter(self._values)

    class FakeConnection:
        def __init__(self) -> None:
            self.executed: list[tuple[str, dict[str, object] | None]] = []
            self.column_results = [
                {"user_id", "status", "role", "created_at"},
                {
                    "user_id",
                    "platform",
                    "platform_user_id",
                    "status",
                    "connected_at",
                    "disconnected_at",
                },
            ]

        def execute(self, statement, params=None):
            sql = str(statement)
            self.executed.append((sql, params))
            if "information_schema.columns" in sql:
                return FakeResult(self.column_results.pop(0))
            return FakeResult([])

    class FakeBegin:
        def __init__(self, connection: FakeConnection) -> None:
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeEngine:
        def __init__(self) -> None:
            self.connection = FakeConnection()

        def begin(self):
            return FakeBegin(self.connection)

        def dispose(self) -> None:
            return None

    fake_engine = FakeEngine()

    class FakeContainer:
        def __init__(self, config: AppConfig) -> None:
            self.config = config

        def build_engine_factory(self):
            return SimpleNamespace(create=lambda: fake_engine)

    monkeypatch.setitem(sys.modules, "tailmate.bootstrap.container", SimpleNamespace(AppContainer=FakeContainer))

    module.ensure_local_user_exists(build_local_config(tmp_path), "user-2")

    user_insert = next(
        params
        for sql, params in fake_engine.connection.executed
        if "INSERT INTO users" in sql
    )
    connection_insert = next(
        params
        for sql, params in fake_engine.connection.executed
        if "INSERT INTO user_platform_connections" in sql
    )
    assert user_insert == {"user_id": "user-2", "status": "active", "role": "owner"}
    assert connection_insert == {
        "user_id": "user-2",
        "platform": "web",
        "platform_user_id": "user-2",
        "status": "active",
    }


@pytest.fixture(autouse=True)
def clear_local_dev_module():
    yield
    sys.modules.pop("tailmate.entrypoints.local_env", None)
    sys.modules.pop("tailmate.entrypoints.local_dev", None)


def test_database_engine_factory_returns_fresh_engines() -> None:
    factory = DatabaseEngineFactory("sqlite:///:memory:")

    first = factory.create()
    second = factory.create()

    assert first is not second

    first.dispose()
    second.dispose()
