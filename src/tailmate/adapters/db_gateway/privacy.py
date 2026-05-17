"""User privacy export and deletion helpers for the gateway."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from typing import Any

from sqlalchemy import delete, select

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import (
    conversation_sessions,
    dog_profiles,
    media_assets,
    profile_enrichment_log,
    public_query_rate_limit_events,
    user_platform_connections,
    users,
)
from tailmate.agent_runtime.ports.blob_store import BlobStore
from tailmate.contracts.errors import AdapterError, ConfigurationError, DomainError, NotFoundError
from tailmate.tracing import start_span


def _normalize_user_id(user_id: str) -> str:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        raise DomainError("user_id is required for privacy operations.")
    return normalized_user_id


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_serialize_value(item) for item in value]
    return str(value)


def _serialize_row(mapping: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _serialize_value(value)
        for key, value in mapping.items()
    }


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _session_scope_pattern(user_id: str) -> str:
    return f"{_escape_like(user_id)}__%"


@dataclass(frozen=True)
class UserPrivacyGatewayService:
    """Export and erase a user's persisted data across gateway-owned systems."""

    engine_factory: DatabaseEngineFactory
    blob_store: BlobStore
    firebase_user_deleter: Callable[[str], None]

    def export_user_data(self, *, user_id: str) -> dict[str, Any]:
        normalized_user_id = _normalize_user_id(user_id)
        with start_span(
            "db.privacy.export_user_data",
            attributes={"db.system": "postgresql", "db.operation": "select"},
        ):
            snapshot = self._load_snapshot(normalized_user_id)
            return {
                **snapshot,
                "format_version": "v1",
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }

    def delete_user_data(self, *, user_id: str) -> dict[str, Any]:
        normalized_user_id = _normalize_user_id(user_id)
        with start_span(
            "db.privacy.delete_user_data",
            attributes={"db.system": "postgresql", "db.operation": "delete"},
        ):
            snapshot = self._load_snapshot(normalized_user_id)
            media_paths = [
                str(asset["logical_path"])
                for asset in snapshot["media_assets"]
                if asset.get("logical_path")
            ]

            dog_ids = [
                str(profile["id"])
                for profile in snapshot["dog_profiles"]
                if profile.get("id") is not None
            ]
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    if dog_ids:
                        connection.execute(
                            delete(profile_enrichment_log).where(
                                profile_enrichment_log.c.dog_id.in_(dog_ids)
                            )
                        )
                        connection.execute(
                            delete(media_assets).where(media_assets.c.dog_id.in_(dog_ids))
                        )
                        connection.execute(
                            delete(dog_profiles).where(dog_profiles.c.user_id == normalized_user_id)
                        )

                    connection.execute(
                        delete(conversation_sessions).where(
                            conversation_sessions.c.session_id.like(
                                _session_scope_pattern(normalized_user_id),
                                escape="\\",
                            )
                        )
                    )
                    connection.execute(
                        delete(user_platform_connections).where(
                            user_platform_connections.c.user_id == normalized_user_id
                        )
                    )
                    connection.execute(
                        delete(public_query_rate_limit_events).where(
                            public_query_rate_limit_events.c.user_id == normalized_user_id
                        )
                    )
                    connection.execute(delete(users).where(users.c.user_id == normalized_user_id))
            finally:
                engine.dispose()

            for logical_path in media_paths:
                self.blob_store.delete(logical_path)

            self.firebase_user_deleter(normalized_user_id)

            return {
                "deleted": True,
                "user_id": normalized_user_id,
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "counts": {
                    "platform_connections": len(snapshot["platform_connections"]),
                    "dog_profiles": len(snapshot["dog_profiles"]),
                    "profile_enrichment_log": len(snapshot["profile_enrichment_log"]),
                    "media_assets": len(snapshot["media_assets"]),
                    "conversation_sessions": len(snapshot["conversation_sessions"]),
                    "public_query_rate_limit_events": len(
                        snapshot["public_query_rate_limit_events"]
                    ),
                },
                "blob_objects_deleted": len(media_paths),
                "firebase_user_deleted": True,
            }

    def _load_snapshot(self, user_id: str) -> dict[str, Any]:
        with start_span(
            "db.privacy.load_snapshot",
            attributes={"db.system": "postgresql", "db.operation": "select"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    user_row = connection.execute(
                    select(
                        users.c.user_id,
                        users.c.status,
                        users.c.role,
                        users.c.created_at,
                    ).where(users.c.user_id == user_id)
                ).mappings().first()
                    if user_row is None:
                        raise NotFoundError("The requested user does not exist.")

                    platform_rows = connection.execute(
                    select(
                        user_platform_connections.c.user_id,
                        user_platform_connections.c.platform,
                        user_platform_connections.c.platform_user_id,
                        user_platform_connections.c.status,
                        user_platform_connections.c.connected_at,
                        user_platform_connections.c.disconnected_at,
                    )
                    .where(user_platform_connections.c.user_id == user_id)
                    .order_by(user_platform_connections.c.platform.asc())
                ).mappings().all()

                    profile_rows = connection.execute(
                    select(
                        dog_profiles.c.id,
                        dog_profiles.c.user_id,
                        dog_profiles.c.name,
                        dog_profiles.c.breed,
                        dog_profiles.c.age_months,
                        dog_profiles.c.weight_kg,
                        dog_profiles.c.sex,
                        dog_profiles.c.neutered,
                        dog_profiles.c.medical_history,
                        dog_profiles.c.allergies,
                        dog_profiles.c.current_medications,
                        dog_profiles.c.temperament,
                        dog_profiles.c.activity_level,
                        dog_profiles.c.diet,
                        dog_profiles.c.raw_notes,
                        dog_profiles.c.created_at,
                        dog_profiles.c.updated_at,
                    )
                    .where(dog_profiles.c.user_id == user_id)
                    .order_by(dog_profiles.c.created_at.asc(), dog_profiles.c.id.asc())
                ).mappings().all()

                    dog_ids = [str(row["id"]) for row in profile_rows]

                    if dog_ids:
                        enrichment_rows = connection.execute(
                        select(
                            profile_enrichment_log.c.id,
                            profile_enrichment_log.c.dog_id,
                            profile_enrichment_log.c.source_message,
                            profile_enrichment_log.c.strategy_used,
                            profile_enrichment_log.c.extracted_fields,
                            profile_enrichment_log.c.confidence,
                            profile_enrichment_log.c.created_at,
                        )
                        .where(profile_enrichment_log.c.dog_id.in_(dog_ids))
                        .order_by(
                            profile_enrichment_log.c.created_at.asc(),
                            profile_enrichment_log.c.id.asc(),
                        )
                    ).mappings().all()

                        media_rows = connection.execute(
                        select(
                            media_assets.c.media_id,
                            media_assets.c.dog_id,
                            media_assets.c.session_id,
                            media_assets.c.resource_kind,
                            media_assets.c.media_kind,
                            media_assets.c.content_type,
                            media_assets.c.source_filename,
                            media_assets.c.logical_path,
                            media_assets.c.media_ref,
                            media_assets.c.uploaded_by,
                            media_assets.c.sanitization_method,
                            media_assets.c.sanitization_status,
                            media_assets.c.metadata_stripped,
                            media_assets.c.byte_size,
                            media_assets.c.created_at,
                        )
                        .where(media_assets.c.dog_id.in_(dog_ids))
                        .order_by(media_assets.c.created_at.asc(), media_assets.c.media_id.asc())
                    ).mappings().all()
                    else:
                        enrichment_rows = []
                        media_rows = []

                    session_rows = connection.execute(
                    select(
                        conversation_sessions.c.session_id,
                        conversation_sessions.c.turns,
                        conversation_sessions.c.attributes,
                    )
                    .where(
                        conversation_sessions.c.session_id.like(
                            _session_scope_pattern(user_id),
                            escape="\\",
                        )
                    )
                    .order_by(conversation_sessions.c.session_id.asc())
                ).mappings().all()

                    rate_limit_rows = connection.execute(
                    select(
                        public_query_rate_limit_events.c.user_id,
                        public_query_rate_limit_events.c.occurred_at,
                    )
                    .where(public_query_rate_limit_events.c.user_id == user_id)
                    .order_by(
                        public_query_rate_limit_events.c.occurred_at.asc(),
                        public_query_rate_limit_events.c.id.asc(),
                    )
                ).mappings().all()
            finally:
                engine.dispose()

        return {
            "user": _serialize_row(user_row),
            "platform_connections": [_serialize_row(row) for row in platform_rows],
            "dog_profiles": [_serialize_row(row) for row in profile_rows],
            "profile_enrichment_log": [_serialize_row(row) for row in enrichment_rows],
            "media_assets": [_serialize_row(row) for row in media_rows],
            "conversation_sessions": [_serialize_row(row) for row in session_rows],
            "public_query_rate_limit_events": [_serialize_row(row) for row in rate_limit_rows],
        }


def build_firebase_user_deleter() -> Callable[[str], None]:
    """Build the Firebase account deleter used by the privacy delete endpoint."""

    try:
        import firebase_admin
        from firebase_admin import auth
    except ImportError as exc:  # pragma: no cover - exercised through dependency wiring
        raise ConfigurationError(
            "firebase-admin must be installed to delete Firebase-authenticated users."
        ) from exc

    firebase_app = None
    firebase_app_lock = Lock()

    def _delete_user(user_id: str) -> None:
        nonlocal firebase_app

        normalized_user_id = _normalize_user_id(user_id)
        if firebase_app is None:
            with firebase_app_lock:
                if firebase_app is None:
                    try:
                        firebase_app = firebase_admin.get_app()
                    except ValueError:
                        firebase_app = firebase_admin.initialize_app()

        try:
            auth.delete_user(normalized_user_id, app=firebase_app)
        except Exception as exc:  # pragma: no cover - depends on external SDK/runtime wiring
            if exc.__class__.__name__ == "UserNotFoundError":
                return
            raise AdapterError(f"Failed to delete Firebase user '{normalized_user_id}'.") from exc

    return _delete_user
