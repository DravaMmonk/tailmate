"""Pydantic contracts for the dog_profile skill."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


DOG_PROFILE_FIELD_NAMES = frozenset(
    {
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
    }
)
LIST_FIELD_NAMES = frozenset({"medical_history", "allergies", "current_medications", "raw_notes"})
TEXT_FIELD_NAMES = frozenset({"name", "breed", "sex", "temperament", "activity_level", "diet"})
PATCHABLE_FIELD_NAMES = DOG_PROFILE_FIELD_NAMES - {"name"}


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, list):
        raw_items = value
    else:
        raise TypeError("Expected a string or a list of strings.")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        text = str(item).strip()
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text)
    return normalized or None


def _normalize_sex(value: Any) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    lowered = normalized.casefold()
    if lowered in {"male", "boy", "m", "公", "公狗", "弟弟", "男", "男孩"}:
        return "male"
    if lowered in {"female", "girl", "f", "母", "母狗", "妹妹", "女", "女孩"}:
        return "female"
    return normalized


class DogProfilePatch(BaseModel):
    """Partial profile fields that can be created or enriched."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    breed: str | None = None
    age_months: int | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)
    sex: str | None = None
    neutered: bool | None = None
    medical_history: list[str] | None = None
    allergies: list[str] | None = None
    current_medications: list[str] | None = None
    temperament: str | None = None
    activity_level: str | None = None
    diet: str | None = None
    raw_notes: list[str] | None = None

    @field_validator(*TEXT_FIELD_NAMES, mode="before")
    @classmethod
    def _validate_text_fields(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("sex", mode="before")
    @classmethod
    def _validate_sex(cls, value: Any) -> str | None:
        return _normalize_sex(value)

    @field_validator("medical_history", "allergies", "current_medications", "raw_notes", mode="before")
    @classmethod
    def _validate_list_fields(cls, value: Any) -> list[str] | None:
        return _normalize_string_list(value)

    @field_validator("weight_kg", mode="before")
    @classmethod
    def _validate_weight(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        return round(float(value), 2)

    def to_update_dict(self) -> dict[str, Any]:
        """Return the non-null patch fields as a plain JSON-serializable dict."""

        return self.model_dump(mode="json", exclude_none=True)


class DogProfile(BaseModel):
    """Persisted dog profile record."""

    model_config = ConfigDict(extra="forbid")

    dog_id: str | None = None
    user_id: str | None = None
    name: str = Field(min_length=1)
    breed: str | None = None
    age_months: int | None = Field(default=None, ge=0)
    weight_kg: float | None = Field(default=None, ge=0)
    sex: str | None = None
    neutered: bool | None = None
    medical_history: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    temperament: str | None = None
    activity_level: str | None = None
    diet: str | None = None
    raw_notes: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator(*TEXT_FIELD_NAMES, mode="before")
    @classmethod
    def _validate_text_fields(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("name", mode="before")
    @classmethod
    def _validate_name(cls, value: Any) -> str:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            raise ValueError("name is required.")
        return normalized

    @field_validator("sex", mode="before")
    @classmethod
    def _validate_sex(cls, value: Any) -> str | None:
        return _normalize_sex(value)

    @field_validator("medical_history", "allergies", "current_medications", "raw_notes", mode="before")
    @classmethod
    def _validate_list_fields(cls, value: Any) -> list[str]:
        normalized = _normalize_string_list(value)
        return normalized or []

    @field_validator("weight_kg", mode="before")
    @classmethod
    def _validate_weight(cls, value: Any) -> float | None:
        if value is None or value == "":
            return None
        return round(float(value), 2)

    def to_storage_dict(self) -> dict[str, Any]:
        """Return the profile fields in database-column format."""

        payload = self.model_dump(mode="python")
        payload["id"] = payload.pop("dog_id")
        return payload


class CreateDogProfileInput(DogProfilePatch):
    """Input contract for dog profile creation."""

    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    name: str = Field(min_length=1)

    @field_validator("session_id", "user_id", "name", mode="before")
    @classmethod
    def _validate_text_identity_fields(cls, value: Any) -> str:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            raise ValueError("session_id, user_id, and name are required.")
        return normalized


class CreateDogProfileOutput(BaseModel):
    """Output contract for dog profile creation."""

    model_config = ConfigDict(extra="forbid")

    dog_id: str
    profile_summary: str
    created_at: datetime


class ExtractionResult(BaseModel):
    """Normalized extractor output shared by all extraction strategies."""

    model_config = ConfigDict(extra="forbid")

    structured_fields: dict[str, Any] = Field(default_factory=dict)
    raw_note: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    strategy_used: str

    @field_validator("structured_fields", mode="before")
    @classmethod
    def _validate_structured_fields(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("structured_fields must be a mapping.")
        return normalize_dog_profile_patch(value)

    @field_validator("raw_note", mode="before")
    @classmethod
    def _validate_raw_note(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)


class EnrichDogProfileInput(BaseModel):
    """Input contract for dog profile enrichment."""

    model_config = ConfigDict(extra="forbid")

    dog_id: str = Field(min_length=1)
    requesting_user_id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    current_profile: DogProfile | None = None

    @field_validator("dog_id", "requesting_user_id", "user_message", mode="before")
    @classmethod
    def _validate_text_fields(cls, value: Any) -> str:
        normalized = _normalize_optional_text(value)
        if normalized is None:
            raise ValueError("dog_id, requesting_user_id, and user_message are required.")
        return normalized


class EnrichDogProfileOutput(BaseModel):
    """Output contract for dog profile enrichment."""

    model_config = ConfigDict(extra="forbid")

    updated_fields: dict[str, Any] = Field(default_factory=dict)
    raw_note: str | None = None
    extraction_strategy_used: str

    @field_validator("updated_fields", mode="before")
    @classmethod
    def _validate_updated_fields(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError("updated_fields must be a mapping.")
        return normalize_dog_profile_patch(value)

    @field_validator("raw_note", mode="before")
    @classmethod
    def _validate_raw_note(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)


DogProfileToolRequest = CreateDogProfileInput | EnrichDogProfileInput
DogProfileToolResult = CreateDogProfileOutput | EnrichDogProfileOutput


def normalize_dog_profile_patch(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a partial profile update payload."""

    return DogProfilePatch.model_validate(dict(payload)).to_update_dict()


def normalize_create_dog_profile_input(payload: Mapping[str, Any]) -> CreateDogProfileInput:
    """Validate the creation payload."""

    return CreateDogProfileInput.model_validate(dict(payload))


def normalize_create_dog_profile_output(payload: Mapping[str, Any]) -> CreateDogProfileOutput:
    """Validate the creation result payload."""

    return CreateDogProfileOutput.model_validate(dict(payload))


def normalize_dog_profile(payload: Mapping[str, Any]) -> DogProfile:
    """Validate a persisted dog profile payload."""

    normalized = dict(payload)
    if "id" in normalized and "dog_id" not in normalized:
        normalized["dog_id"] = normalized.pop("id")
    return DogProfile.model_validate(normalized)


def normalize_enrich_dog_profile_input(payload: Mapping[str, Any]) -> EnrichDogProfileInput:
    """Validate the enrichment request payload."""

    return EnrichDogProfileInput.model_validate(dict(payload))


def normalize_enrich_dog_profile_output(payload: Mapping[str, Any]) -> EnrichDogProfileOutput:
    """Validate the enrichment result payload."""

    return EnrichDogProfileOutput.model_validate(dict(payload))


def normalize_extraction_result(payload: Mapping[str, Any]) -> ExtractionResult:
    """Validate the normalized extractor result payload."""

    return ExtractionResult.model_validate(dict(payload))


def render_profile_summary(profile: DogProfile) -> str:
    """Build a concise summary string for downstream caller surfaces."""

    summary_parts = [profile.name]
    if profile.breed:
        summary_parts.append(profile.breed)
    if profile.age_months is not None:
        summary_parts.append(f"{profile.age_months} months")
    if profile.weight_kg is not None:
        summary_parts.append(f"{profile.weight_kg:g} kg")
    return " | ".join(summary_parts)
