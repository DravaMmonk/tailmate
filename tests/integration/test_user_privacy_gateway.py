from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import (
    conversation_sessions,
    dog_profiles,
    media_assets,
    metadata,
    profile_enrichment_log,
    public_query_rate_limit_events,
    user_platform_connections,
    users,
)
from tailmate.adapters.db_gateway.privacy import UserPrivacyGatewayService
from tailmate.contracts.errors import NotFoundError


class FakeBlobStore:
    def __init__(self) -> None:
        self.deleted_paths: list[str] = []

    def put(self, logical_path: str, content_type: str, payload: bytes) -> str:
        del content_type, payload
        return logical_path

    def resolve_resource(self, logical_path: str) -> str:
        return f"gs://tailmate-media/{logical_path}"

    def delete(self, logical_path: str) -> None:
        self.deleted_paths.append(logical_path)


def build_privacy_service(tmp_path: Path) -> tuple[UserPrivacyGatewayService, Path, FakeBlobStore, list[str]]:
    database_path = tmp_path / "privacy.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    metadata.create_all(
        engine,
        tables=[
            users,
            user_platform_connections,
            dog_profiles,
            profile_enrichment_log,
            media_assets,
            conversation_sessions,
            public_query_rate_limit_events,
        ],
    )

    now = datetime(2026, 3, 29, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            users.insert(),
            [
                {"user_id": "user-1", "status": "active", "role": "owner", "created_at": now},
                {"user_id": "user-2", "status": "active", "role": "owner", "created_at": now},
            ],
        )
        connection.execute(
            user_platform_connections.insert(),
            [
                {
                    "user_id": "user-1",
                    "platform": "web",
                    "platform_user_id": "user-1",
                    "status": "active",
                    "connected_at": now,
                },
                {
                    "user_id": "user-1",
                    "platform": "telegram",
                    "platform_user_id": "telegram-1",
                    "status": "active",
                    "connected_at": now,
                },
                {
                    "user_id": "user-2",
                    "platform": "web",
                    "platform_user_id": "user-2",
                    "status": "active",
                    "connected_at": now,
                },
            ],
        )
        connection.execute(
            dog_profiles.insert(),
            [
                {
                    "id": "dog-1",
                    "user_id": "user-1",
                    "name": "DouDou",
                    "medical_history": ["allergy"],
                    "allergies": [],
                    "current_medications": [],
                    "raw_notes": ["Loves carrots"],
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": "dog-2",
                    "user_id": "user-2",
                    "name": "Buddy",
                    "medical_history": [],
                    "allergies": [],
                    "current_medications": [],
                    "raw_notes": [],
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        )
        connection.execute(
            profile_enrichment_log.insert(),
            [
                {
                    "id": "enrich-1",
                    "dog_id": "dog-1",
                    "source_message": "DouDou has a chicken allergy.",
                    "strategy_used": "rule",
                    "extracted_fields": {"allergies": ["chicken"]},
                    "confidence": 0.9,
                    "created_at": now,
                },
                {
                    "id": "enrich-2",
                    "dog_id": "dog-2",
                    "source_message": "Buddy is energetic.",
                    "strategy_used": "rule",
                    "extracted_fields": {"activity_level": "high"},
                    "confidence": 0.8,
                    "created_at": now,
                },
            ],
        )
        connection.execute(
            media_assets.insert(),
            [
                {
                    "media_id": "media-1",
                    "dog_id": "dog-1",
                    "session_id": "user-1__web__session-1",
                    "resource_kind": "images",
                    "media_kind": "image",
                    "content_type": "image/jpeg",
                    "source_filename": "photo.jpg",
                    "logical_path": "dogs/dog-1/images/photo.jpg",
                    "media_ref": "gs://tailmate-media/dogs/dog-1/images/photo.jpg",
                    "uploaded_by": "writer@test",
                    "sanitization_method": "pillow",
                    "sanitization_status": "sanitized",
                    "metadata_stripped": True,
                    "byte_size": 1234,
                    "created_at": now,
                },
                {
                    "media_id": "media-2",
                    "dog_id": "dog-2",
                    "session_id": "user-2__web__session-1",
                    "resource_kind": "images",
                    "media_kind": "image",
                    "content_type": "image/jpeg",
                    "source_filename": "buddy.jpg",
                    "logical_path": "dogs/dog-2/images/buddy.jpg",
                    "media_ref": "gs://tailmate-media/dogs/dog-2/images/buddy.jpg",
                    "uploaded_by": "writer@test",
                    "sanitization_method": "pillow",
                    "sanitization_status": "sanitized",
                    "metadata_stripped": True,
                    "byte_size": 999,
                    "created_at": now,
                },
            ],
        )
        connection.execute(
            conversation_sessions.insert(),
            [
                {
                    "session_id": "user-1__web__session-1",
                    "turns": [{"role": "user", "message": "hello"}],
                    "attributes": {"dog_id": "dog-1"},
                },
                {
                    "session_id": "user-1__telegram__session-2",
                    "turns": [{"role": "user", "message": "hi from telegram"}],
                    "attributes": {"dog_id": "dog-1"},
                },
                {
                    "session_id": "user-2__web__session-1",
                    "turns": [{"role": "user", "message": "keep me"}],
                    "attributes": {"dog_id": "dog-2"},
                },
            ],
        )
        connection.execute(
            public_query_rate_limit_events.insert(),
            [
                {"user_id": "user-1", "occurred_at": now},
                {"user_id": "user-1", "occurred_at": now},
                {"user_id": "user-2", "occurred_at": now},
            ],
        )
    engine.dispose()

    blob_store = FakeBlobStore()
    deleted_firebase_users: list[str] = []
    service = UserPrivacyGatewayService(
        engine_factory=DatabaseEngineFactory(f"sqlite+pysqlite:///{database_path}"),
        blob_store=blob_store,
        firebase_user_deleter=deleted_firebase_users.append,
    )
    return service, database_path, blob_store, deleted_firebase_users


def test_user_privacy_service_exports_only_requested_owner_data(tmp_path: Path) -> None:
    service, _database_path, _blob_store, _deleted_firebase_users = build_privacy_service(tmp_path)

    payload = service.export_user_data(user_id="user-1")

    assert payload["user"]["user_id"] == "user-1"
    assert payload["format_version"] == "v1"
    assert [connection["platform"] for connection in payload["platform_connections"]] == [
        "telegram",
        "web",
    ]
    assert [profile["id"] for profile in payload["dog_profiles"]] == ["dog-1"]
    assert [entry["dog_id"] for entry in payload["profile_enrichment_log"]] == ["dog-1"]
    assert [asset["dog_id"] for asset in payload["media_assets"]] == ["dog-1"]
    assert {session["session_id"] for session in payload["conversation_sessions"]} == {
        "user-1__telegram__session-2",
        "user-1__web__session-1",
    }
    assert [event["user_id"] for event in payload["public_query_rate_limit_events"]] == [
        "user-1",
        "user-1",
    ]


def test_user_privacy_service_deletes_owner_data_and_keeps_other_users(tmp_path: Path) -> None:
    service, database_path, blob_store, deleted_firebase_users = build_privacy_service(tmp_path)

    deletion = service.delete_user_data(user_id="user-1")

    assert deletion["deleted"] is True
    assert deletion["counts"] == {
        "platform_connections": 2,
        "dog_profiles": 1,
        "profile_enrichment_log": 1,
        "media_assets": 1,
        "conversation_sessions": 2,
        "public_query_rate_limit_events": 2,
    }
    assert blob_store.deleted_paths == ["dogs/dog-1/images/photo.jpg"]
    assert deleted_firebase_users == ["user-1"]

    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    with engine.begin() as connection:
        assert connection.execute(select(users.c.user_id)).scalars().all() == ["user-2"]
        assert connection.execute(select(dog_profiles.c.id)).scalars().all() == ["dog-2"]
        assert connection.execute(select(media_assets.c.media_id)).scalars().all() == ["media-2"]
        assert connection.execute(select(conversation_sessions.c.session_id)).scalars().all() == [
            "user-2__web__session-1"
        ]
        assert connection.execute(
            select(public_query_rate_limit_events.c.user_id).order_by(
                public_query_rate_limit_events.c.id.asc()
            )
        ).scalars().all() == ["user-2"]
    engine.dispose()

    with pytest.raises(NotFoundError, match="does not exist"):
        service.export_user_data(user_id="user-1")


class RecordingBlobStore(FakeBlobStore):
    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    def delete(self, logical_path: str) -> None:
        self._events.append(f"blob_delete:{logical_path}")
        super().delete(logical_path)


class RecordingConnection:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self._events = events
        self._fail = fail

    def execute(self, _statement, *_args, **_kwargs) -> None:
        self._events.append("db_execute")
        if self._fail:
            raise RuntimeError("delete failed")


class RecordingEngine:
    def __init__(self, events: list[str], *, fail: bool = False) -> None:
        self._events = events
        self._fail = fail

    @contextmanager
    def begin(self) -> Iterator[RecordingConnection]:
        self._events.append("db_begin")
        try:
            yield RecordingConnection(self._events, fail=self._fail)
        except Exception:
            self._events.append("db_rollback")
            raise
        self._events.append("db_commit")

    def dispose(self) -> None:
        self._events.append("db_dispose")


class RecordingEngineFactory:
    def __init__(self, engine: RecordingEngine) -> None:
        self._engine = engine

    def create(self) -> RecordingEngine:
        return self._engine


def _build_snapshot() -> dict[str, object]:
    return {
        "user": {"user_id": "user-1"},
        "platform_connections": [{"platform": "web"}],
        "dog_profiles": [{"id": "dog-1"}],
        "profile_enrichment_log": [{"id": "enrich-1"}],
        "media_assets": [{"media_id": "media-1", "logical_path": "dogs/dog-1/images/photo.jpg"}],
        "conversation_sessions": [{"session_id": "user-1__web__session-1"}],
        "public_query_rate_limit_events": [{"user_id": "user-1"}],
    }


def test_user_privacy_service_deletes_external_resources_after_db_commit(monkeypatch) -> None:
    events: list[str] = []
    service = UserPrivacyGatewayService(
        engine_factory=RecordingEngineFactory(RecordingEngine(events)),
        blob_store=RecordingBlobStore(events),
        firebase_user_deleter=lambda user_id: events.append(f"firebase_delete:{user_id}"),
    )
    monkeypatch.setattr(UserPrivacyGatewayService, "_load_snapshot", lambda self, _user_id: _build_snapshot())

    deletion = service.delete_user_data(user_id="user-1")

    assert deletion["deleted"] is True
    assert events == [
        "db_begin",
        "db_execute",
        "db_execute",
        "db_execute",
        "db_execute",
        "db_execute",
        "db_execute",
        "db_execute",
        "db_commit",
        "db_dispose",
        "blob_delete:dogs/dog-1/images/photo.jpg",
        "firebase_delete:user-1",
    ]


def test_user_privacy_service_skips_external_cleanup_when_db_delete_fails(monkeypatch) -> None:
    events: list[str] = []
    service = UserPrivacyGatewayService(
        engine_factory=RecordingEngineFactory(RecordingEngine(events, fail=True)),
        blob_store=RecordingBlobStore(events),
        firebase_user_deleter=lambda user_id: events.append(f"firebase_delete:{user_id}"),
    )
    monkeypatch.setattr(UserPrivacyGatewayService, "_load_snapshot", lambda self, _user_id: _build_snapshot())

    with pytest.raises(RuntimeError, match="delete failed"):
        service.delete_user_data(user_id="user-1")

    assert events == [
        "db_begin",
        "db_execute",
        "db_rollback",
        "db_dispose",
    ]
