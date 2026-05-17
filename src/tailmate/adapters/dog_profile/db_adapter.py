"""Database-backed dog profile persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from uuid import uuid4

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import dog_profiles, profile_enrichment_log
from tailmate.contracts.audit import AuditLogger
from tailmate.contracts.authz import assert_owner
from tailmate.contracts.dog_profile import (
    CreateDogProfileInput,
    CreateDogProfileOutput,
    DogProfile,
    EnrichDogProfileInput,
    EnrichDogProfileOutput,
    ExtractionResult,
    normalize_dog_profile,
    render_profile_summary,
)
from tailmate.contracts.errors import AdapterError, DomainError
from tailmate.observability import generate_trace_id, get_log_context
from sqlalchemy import delete, select, update


logger = logging.getLogger(__name__)

LIST_FIELD_NAMES = ("medical_history", "allergies", "current_medications")
PROFILE_MUTABLE_FIELDS = (
    "user_id",
    "name",
    "breed",
    "age_months",
    "weight_kg",
    "sex",
    "neutered",
    "medical_history",
    "allergies",
    "current_medications",
    "temperament",
    "activity_level",
    "diet",
    "raw_notes",
)


@dataclass(frozen=True)
class ProfileMutation:
    """Merged view of one enrichment application."""

    updated_profile: DogProfile
    updated_fields: dict[str, object]
    stored_raw_note: str | None
    touched: bool


def _merge_unique_strings(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    seen = {item.casefold() for item in existing}
    for item in incoming:
        lowered = item.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(item)
    return merged


def apply_extraction_result(
    current_profile: DogProfile,
    extraction_result: ExtractionResult,
) -> ProfileMutation:
    """Apply a normalized extraction result onto the current profile snapshot."""

    updated_fields: dict[str, object] = {}
    profile_updates: dict[str, object] = {}

    for field_name, value in extraction_result.structured_fields.items():
        if value is None:
            continue
        existing_value = getattr(current_profile, field_name)
        if field_name in LIST_FIELD_NAMES:
            if not isinstance(value, list):
                continue
            merged_list = _merge_unique_strings(list(existing_value), value)
            if merged_list != existing_value:
                profile_updates[field_name] = merged_list
                updated_fields[field_name] = merged_list
            continue
        if value != existing_value:
            profile_updates[field_name] = value
            updated_fields[field_name] = value

    stored_raw_note: str | None = None
    if extraction_result.raw_note:
        merged_notes = _merge_unique_strings(current_profile.raw_notes, [extraction_result.raw_note])
        if merged_notes != current_profile.raw_notes:
            profile_updates["raw_notes"] = merged_notes
            stored_raw_note = extraction_result.raw_note

    touched = bool(profile_updates)
    if touched:
        profile_updates["updated_at"] = datetime.now(timezone.utc)
    updated_profile = current_profile.model_copy(update=profile_updates)
    return ProfileMutation(
        updated_profile=updated_profile,
        updated_fields=updated_fields,
        stored_raw_note=stored_raw_note,
        touched=touched,
    )


@dataclass
class DatabaseDogProfileDBAdapter:
    """Persist dog profiles through direct PostgreSQL access."""

    engine_factory: DatabaseEngineFactory
    audit_logger: AuditLogger | None = None

    @staticmethod
    def _resolve_trace_id() -> str:
        return (get_log_context().trace_id or "").strip() or generate_trace_id()

    def _record_audit_event(self, **event: object) -> None:
        if self.audit_logger is None:
            return
        try:
            self.audit_logger.record(**event)
        except Exception as exc:
            logger.warning(
                "dog_profile_db_adapter.audit_record_failed for action=%s entity_id=%s with %s: %s",
                event.get("action"),
                event.get("entity_id"),
                type(exc).__name__,
                exc,
            )

    def _load_raw_profile_row(self, dog_id: str) -> dict[str, object] | None:
        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                return (
                    connection.execute(
                        select(*dog_profiles.c).where(dog_profiles.c.id == dog_id)
                    )
                    .mappings()
                    .first()
                )
        except Exception as exc:
            logger.exception(
                "dog_profile_db_adapter._load_raw_profile_row failed for dog_id=%s with %s: %s",
                dog_id,
                type(exc).__name__,
                exc,
            )
            raise AdapterError(f"Failed to load dog profile '{dog_id}'.") from exc
        finally:
            engine.dispose()

    def create_profile(self, request: CreateDogProfileInput) -> CreateDogProfileOutput:
        created_at = datetime.now(timezone.utc)
        dog_id = str(uuid4())
        profile = DogProfile.model_validate(
            {
                **request.model_dump(mode="python", exclude={"session_id"}, exclude_none=True),
                "dog_id": dog_id,
                "created_at": created_at,
                "updated_at": created_at,
                "medical_history": request.medical_history or [],
                "allergies": request.allergies or [],
                "current_medications": request.current_medications or [],
                "raw_notes": request.raw_notes or [],
            }
        )
        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                connection.execute(dog_profiles.insert().values(profile.to_storage_dict()))
        except Exception as exc:
            logger.exception(
                "dog_profile_db_adapter.create_profile failed for name=%s with %s: %s",
                request.name,
                type(exc).__name__,
                exc,
            )
            raise AdapterError(f"Failed to create dog profile for '{request.name}'.") from exc
        finally:
            engine.dispose()

        self._record_audit_event(
            trace_id=self._resolve_trace_id(),
            user_id=profile.user_id,
            entity_type="dog_profile",
            entity_id=dog_id,
            action="create",
            before=None,
            after=profile.model_dump(mode="json"),
        )

        return CreateDogProfileOutput(
            dog_id=dog_id,
            profile_summary=render_profile_summary(profile),
            created_at=created_at,
        )

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None:
        row = self._load_raw_profile_row(dog_id)
        if row is None:
            return None
        assert_owner(
            str(row["user_id"]),
            requesting_user_id,
            resource_label=f"dog profile '{dog_id}'",
        )
        return normalize_dog_profile(row)

    def list_profiles(self, *, requesting_user_id: str) -> list[DogProfile]:
        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                rows = (
                    connection.execute(
                        select(*dog_profiles.c)
                        .where(dog_profiles.c.user_id == requesting_user_id)
                        .order_by(
                            dog_profiles.c.updated_at.desc(),
                            dog_profiles.c.created_at.desc(),
                            dog_profiles.c.name.asc(),
                        )
                    )
                    .mappings()
                    .all()
                )
        except Exception as exc:
            logger.exception(
                "dog_profile_db_adapter.list_profiles failed for user_id=%s with %s: %s",
                requesting_user_id,
                type(exc).__name__,
                exc,
            )
            raise AdapterError(
                f"Failed to list dog profiles for user '{requesting_user_id}'."
            ) from exc
        finally:
            engine.dispose()

        return [normalize_dog_profile(row) for row in rows]

    def delete_profile(self, dog_id: str) -> None:
        """Delete a dog profile record by id."""

        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                connection.execute(delete(dog_profiles).where(dog_profiles.c.id == dog_id))
        except Exception as exc:
            logger.exception(
                "dog_profile_db_adapter.delete_profile failed for dog_id=%s with %s: %s",
                dog_id,
                type(exc).__name__,
                exc,
            )
            raise AdapterError(f"Failed to delete dog profile '{dog_id}'.") from exc
        finally:
            engine.dispose()

    def enrich_profile(
        self,
        request: EnrichDogProfileInput,
        extraction_result: ExtractionResult,
    ) -> EnrichDogProfileOutput:
        current_profile = self.load_profile(
            request.dog_id,
            requesting_user_id=request.requesting_user_id,
        )
        if current_profile is None:
            raise DomainError(f"Dog profile '{request.dog_id}' does not exist.")

        mutation = apply_extraction_result(current_profile, extraction_result)
        engine = self.engine_factory.create()
        try:
            with engine.begin() as connection:
                if mutation.touched:
                    connection.execute(
                        update(dog_profiles)
                        .where(dog_profiles.c.id == request.dog_id)
                        .values(
                            **mutation.updated_profile.model_dump(
                                mode="python",
                                include=set(PROFILE_MUTABLE_FIELDS) | {"updated_at"},
                            )
                        )
                    )
                connection.execute(
                    profile_enrichment_log.insert().values(
                        id=str(uuid4()),
                        dog_id=request.dog_id,
                        source_message=request.user_message,
                        strategy_used=extraction_result.strategy_used,
                        extracted_fields=extraction_result.structured_fields,
                        confidence=extraction_result.confidence,
                    )
                )
        except Exception as exc:
            logger.exception(
                "dog_profile_db_adapter.enrich_profile failed for dog_id=%s with %s: %s",
                request.dog_id,
                type(exc).__name__,
                exc,
            )
            raise AdapterError(f"Failed to enrich dog profile '{request.dog_id}'.") from exc
        finally:
            engine.dispose()

        if mutation.touched:
            self._record_audit_event(
                trace_id=self._resolve_trace_id(),
                user_id=current_profile.user_id,
                entity_type="dog_profile",
                entity_id=request.dog_id,
                action="update",
                before=current_profile.model_dump(mode="json"),
                after=mutation.updated_profile.model_dump(mode="json"),
            )

        return EnrichDogProfileOutput(
            updated_fields=mutation.updated_fields,
            raw_note=mutation.stored_raw_note,
            extraction_strategy_used=extraction_result.strategy_used,
        )
