from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import user_platform_connections, users
from tailmate.adapters.db_gateway.identity import (
    DatabaseUserIdentityResolver,
    ResolvedPlatformIdentity,
    build_internal_session_id,
    generate_external_session_id,
)
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError


def test_build_internal_session_id_namespaces_user_platform_and_external_id() -> None:
    assert (
        build_internal_session_id(
            user_id=" user-1 ",
            platform=" web ",
            external_conversation_id=" client-session ",
        )
        == "user-1__web__client-session"
    )


def test_generate_external_session_id_uses_public_prefix() -> None:
    generated = generate_external_session_id()

    assert generated.startswith("session-")
    assert len(generated) > len("session-")


def test_resolve_platform_identity_joins_master_account_and_connection() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "identity.db"
        database_url = f"sqlite+pysqlite:///{database_path}"
        engine = create_engine(database_url)
        users.create(engine)
        user_platform_connections.create(engine)
        with engine.begin() as connection:
            connection.execute(
                users.insert().values(
                    user_id="user-1",
                    status="active",
                    role="owner",
                )
            )
            connection.execute(
                user_platform_connections.insert().values(
                    user_id="user-1",
                    platform="telegram",
                    platform_user_id="tg-42",
                    status="active",
                )
            )
        resolver = DatabaseUserIdentityResolver(
            engine_factory=DatabaseEngineFactory(database_url)
        )
        resolved = resolver.resolve_platform_identity(
            platform="telegram",
            platform_user_id="tg-42",
        )

        assert resolved is not None
        assert resolved.user_id == "user-1"
        assert resolved.status == "active"
        assert resolved.platform == "telegram"
        assert resolved.platform_user_id == "tg-42"
        assert resolved.connection_status == "active"


def test_register_web_user_is_idempotent_for_existing_user_row() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "identity.db"
        database_url = f"sqlite+pysqlite:///{database_path}"
        engine = create_engine(database_url)
        users.create(engine)
        user_platform_connections.create(engine)
        with engine.begin() as connection:
            connection.execute(
                users.insert().values(
                    user_id="user-1",
                    status="pending",
                    role="owner",
                )
            )

        resolver = DatabaseUserIdentityResolver(
            engine_factory=DatabaseEngineFactory(database_url)
        )
        resolved = resolver.register_web_user(firebase_uid="user-1")

        assert resolved.user_id == "user-1"
        assert resolved.platform == "web"
        assert resolved.platform_user_id == "user-1"
        assert resolved.connection_status == "active"


def test_register_web_user_wraps_existing_user_insert_in_savepoint(monkeypatch) -> None:
    calls: list[str] = []

    class FakeNestedTransaction:
        def __enter__(self) -> None:
            calls.append("begin_nested")

        def __exit__(self, exc_type, exc, tb) -> bool:
            calls.append(f"end_nested:{exc_type.__name__ if exc_type else 'none'}")
            return False

    class FakeConnection:
        def begin_nested(self) -> FakeNestedTransaction:
            return FakeNestedTransaction()

        def execute(self, statement, *args: Any, **kwargs: Any):
            del args, kwargs
            calls.append(str(statement))
            raise IntegrityError("INSERT INTO users", {}, Exception("duplicate key"))

    class FakeTransaction:
        def __enter__(self) -> FakeConnection:
            calls.append("begin")
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb) -> bool:
            calls.append("end")
            return False

    class FakeEngine:
        def begin(self) -> FakeTransaction:
            return FakeTransaction()

        def dispose(self) -> None:
            calls.append("dispose")

    class FakeEngineFactory:
        def create(self) -> FakeEngine:
            return FakeEngine()

    resolver = DatabaseUserIdentityResolver(engine_factory=FakeEngineFactory())  # type: ignore[arg-type]
    monkeypatch.setattr(
        DatabaseUserIdentityResolver,
        "_upsert_platform_connection",
        staticmethod(lambda *args, **kwargs: calls.append("upsert_platform_connection")),
    )
    monkeypatch.setattr(
        DatabaseUserIdentityResolver,
        "resolve_platform_identity",
        lambda self, **kwargs: ResolvedPlatformIdentity(
            user_id=str(kwargs["platform_user_id"]),
            status="pending",
            role="owner",
            platform=str(kwargs["platform"]),
            platform_user_id=str(kwargs["platform_user_id"]),
            connection_status="active",
        ),
    )

    resolved = resolver.register_web_user(firebase_uid="user-1")

    assert resolved.user_id == "user-1"
    assert "begin_nested" in calls
    assert "end_nested:IntegrityError" in calls
    assert "upsert_platform_connection" in calls


def test_register_activate_and_disconnect_connection_manage_master_account_state() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "identity.db"
        database_url = f"sqlite+pysqlite:///{database_path}"
        engine = create_engine(database_url)
        users.create(engine)
        user_platform_connections.create(engine)
        resolver = DatabaseUserIdentityResolver(
            engine_factory=DatabaseEngineFactory(database_url)
        )

        registered = resolver.register_web_user(firebase_uid="firebase-user-1")
        activated = resolver.activate_user(user_id="firebase-user-1")
        connected = resolver.upsert_platform_connection(
            user_id="firebase-user-1",
            platform="telegram",
            platform_user_id="telegram-user-1",
            status="active",
        )
        disconnected = resolver.disconnect_platform_connection(
            user_id="firebase-user-1",
            platform="telegram",
        )

        assert registered.status == "pending"
        assert registered.connection_status == "active"
        assert activated.status == "active"
        assert connected.platform == "telegram"
        assert connected.connection_status == "active"
        assert disconnected is not None
        assert disconnected.connection_status == "disconnected"


def test_ensure_active_platform_user_provisions_new_non_web_identity() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "identity.db"
        database_url = f"sqlite+pysqlite:///{database_path}"
        engine = create_engine(database_url)
        users.create(engine)
        user_platform_connections.create(engine)
        resolver = DatabaseUserIdentityResolver(
            engine_factory=DatabaseEngineFactory(database_url)
        )

        identity, created = resolver.ensure_active_platform_user(
            platform="telegram",
            platform_user_id="tg-42",
        )

        assert created is True
        assert identity.status == "active"
        assert identity.platform == "telegram"
        assert identity.platform_user_id == "tg-42"
        assert identity.connection_status == "active"
        assert identity.user_id.startswith("user-")


def test_ensure_active_platform_user_reactivates_existing_connection() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        database_path = Path(temp_dir) / "identity.db"
        database_url = f"sqlite+pysqlite:///{database_path}"
        engine = create_engine(database_url)
        users.create(engine)
        user_platform_connections.create(engine)
        with engine.begin() as connection:
            connection.execute(
                users.insert().values(
                    user_id="user-1",
                    status="pending",
                    role="owner",
                )
            )
            connection.execute(
                user_platform_connections.insert().values(
                    user_id="user-1",
                    platform="telegram",
                    platform_user_id="tg-42",
                    status="disconnected",
                )
            )

        resolver = DatabaseUserIdentityResolver(
            engine_factory=DatabaseEngineFactory(database_url)
        )
        identity, created = resolver.ensure_active_platform_user(
            platform="telegram",
            platform_user_id="tg-42",
        )

        assert created is False
        assert identity.user_id == "user-1"
        assert identity.status == "active"
        assert identity.connection_status == "active"
