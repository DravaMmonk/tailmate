"""Database-backed media asset tracking for sanitized uploads."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import media_assets
from tailmate.contracts.errors import MediaAssetPersistenceError
from tailmate.tracing import start_span


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaAssetRecord:
    """Durable metadata for a sanitized media asset."""

    media_id: str
    dog_id: str
    session_id: str | None
    resource_kind: str
    media_kind: str
    content_type: str
    source_filename: str
    logical_path: str
    media_ref: str
    sanitization_method: str
    sanitization_status: str
    metadata_stripped: bool
    byte_size: int
    uploaded_by: str | None = None


@dataclass
class DatabaseMediaAssetStore:
    """Persist sanitized media references for downstream DB reads."""

    engine_factory: DatabaseEngineFactory

    def save(self, record: MediaAssetRecord) -> None:
        with start_span(
            "db.media_assets.save",
            attributes={"db.system": "postgresql", "db.operation": "insert"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    connection.execute(
                        media_assets.insert().values(
                            media_id=record.media_id,
                            dog_id=record.dog_id,
                            session_id=record.session_id,
                            resource_kind=record.resource_kind,
                            media_kind=record.media_kind,
                            content_type=record.content_type,
                            source_filename=record.source_filename,
                            logical_path=record.logical_path,
                            media_ref=record.media_ref,
                            uploaded_by=record.uploaded_by,
                            sanitization_method=record.sanitization_method,
                            sanitization_status=record.sanitization_status,
                            metadata_stripped=record.metadata_stripped,
                            byte_size=record.byte_size,
                        )
                    )
            except Exception as exc:
                logger.exception(
                    "media_asset_store.save failed for media_id=%s with %s: %s",
                    record.media_id,
                    type(exc).__name__,
                    exc,
                )
                raise MediaAssetPersistenceError(
                    f"Failed to persist sanitized media asset '{record.media_id}'."
                ) from exc
            finally:
                engine.dispose()
