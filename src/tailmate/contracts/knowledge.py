"""Pydantic contracts for verified knowledge base retrieval."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


KnowledgeQueryStatus = Literal["hit", "miss", "out_of_scope"]


def _normalize_required_text(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


class KnowledgeSearchHit(BaseModel):
    """One retrieved chunk plus its similarity metadata."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    category: str | None = None
    score: float = Field(ge=-1.0, le=1.0)
    locale: str = Field(min_length=1)

    @field_validator("content", "source_label", "locale", mode="before")
    @classmethod
    def _validate_required_text(cls, value: Any, info) -> str:
        return _normalize_required_text(value, field_name=str(info.field_name))

    @field_validator("category", mode="before")
    @classmethod
    def _validate_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)


class KnowledgeQueryInput(BaseModel):
    """Normalized input for one knowledge base query attempt."""

    model_config = ConfigDict(extra="forbid")

    user_message: str = Field(min_length=1)
    locale: str = Field(min_length=1)
    dog_context: str | None = None

    @field_validator("user_message", "locale", mode="before")
    @classmethod
    def _validate_required_text(cls, value: Any, info) -> str:
        return _normalize_required_text(value, field_name=str(info.field_name))

    @field_validator("dog_context", mode="before")
    @classmethod
    def _validate_optional_text(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)


class KnowledgeQueryOutput(BaseModel):
    """Normalized output for one knowledge base query attempt."""

    model_config = ConfigDict(extra="forbid")

    status: KnowledgeQueryStatus
    answer: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sources: list[str] = Field(default_factory=list)

    @field_validator("answer", mode="before")
    @classmethod
    def _validate_answer(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("sources", mode="before")
    @classmethod
    def _validate_sources(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise TypeError("sources must be a list of strings.")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            label = str(item or "").strip()
            if not label:
                continue
            lowered = label.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(label)
        return normalized


class KnowledgeSearchRequest(BaseModel):
    """Internal request contract for gateway-backed vector search."""

    model_config = ConfigDict(extra="forbid")

    embedding: list[float] = Field(min_length=1)
    locale: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)

    @field_validator("embedding", mode="before")
    @classmethod
    def _validate_embedding(cls, value: Any) -> list[float]:
        if not isinstance(value, list) or not value:
            raise TypeError("embedding must be a non-empty list of floats.")
        return [float(item) for item in value]

    @field_validator("locale", mode="before")
    @classmethod
    def _validate_locale(cls, value: Any) -> str:
        return _normalize_required_text(value, field_name="locale")


class KnowledgeChunkInput(BaseModel):
    """Normalized input for a managed knowledge chunk."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    content: str = Field(min_length=1)
    source_label: str = Field(min_length=1)
    category: str | None = None
    locale: str = Field(default="en-AU", min_length=1)
    reviewed_at: datetime | None = None

    @field_validator("id", "content", "source_label", "locale", mode="before")
    @classmethod
    def _validate_text(cls, value: Any, info) -> str | None:
        if info.field_name == "id":
            return _normalize_optional_text(value)
        return _normalize_required_text(value, field_name=str(info.field_name))

    @field_validator("category", mode="before")
    @classmethod
    def _validate_category(cls, value: Any) -> str | None:
        return _normalize_optional_text(value)

    @field_validator("reviewed_at", mode="before")
    @classmethod
    def _validate_reviewed_at(cls, value: Any) -> datetime | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        return datetime.fromisoformat(normalized)


class KnowledgeChunkBatchInput(BaseModel):
    """Normalized input for a managed knowledge chunk batch."""

    model_config = ConfigDict(extra="forbid")

    chunks: list[KnowledgeChunkInput] = Field(min_length=1)

    @field_validator("chunks", mode="before")
    @classmethod
    def _validate_chunks(cls, value: Any) -> list[KnowledgeChunkInput]:
        if not isinstance(value, list) or not value:
            raise TypeError("chunks must be a non-empty list of objects.")
        return [KnowledgeChunkInput.model_validate(item) for item in value]


class KnowledgeChunkPreviewInput(BaseModel):
    """Normalized input for managed similarity previews."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    locale: str = Field(default="en-AU", min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)

    @field_validator("query", "locale", mode="before")
    @classmethod
    def _validate_query_text(cls, value: Any, info) -> str:
        return _normalize_required_text(value, field_name=str(info.field_name))


def normalize_knowledge_query_input(payload: Mapping[str, Any]) -> KnowledgeQueryInput:
    """Validate the shared knowledge query input payload."""

    return KnowledgeQueryInput.model_validate(dict(payload))


def normalize_knowledge_query_output(payload: Mapping[str, Any]) -> KnowledgeQueryOutput:
    """Validate the shared knowledge query output payload."""

    return KnowledgeQueryOutput.model_validate(dict(payload))


def normalize_knowledge_search_request(payload: Mapping[str, Any]) -> KnowledgeSearchRequest:
    """Validate the gateway knowledge search request payload."""

    return KnowledgeSearchRequest.model_validate(dict(payload))


def normalize_knowledge_chunk_input(payload: Mapping[str, Any]) -> KnowledgeChunkInput:
    """Validate the managed knowledge chunk payload."""

    return KnowledgeChunkInput.model_validate(dict(payload))


def normalize_knowledge_chunk_batch_input(payload: Any) -> KnowledgeChunkBatchInput:
    """Validate the managed knowledge chunk batch payload."""

    if isinstance(payload, Mapping) and "chunks" in payload:
        payload = payload["chunks"]
    return KnowledgeChunkBatchInput.model_validate({"chunks": payload})


def normalize_knowledge_chunk_preview_input(payload: Mapping[str, Any]) -> KnowledgeChunkPreviewInput:
    """Validate the managed knowledge chunk preview payload."""

    return KnowledgeChunkPreviewInput.model_validate(dict(payload))


def normalize_knowledge_search_hits(payload: Any) -> list[KnowledgeSearchHit]:
    """Validate a list of retrieved knowledge search hits."""

    if payload is None:
        return []
    if not isinstance(payload, list):
        raise TypeError("knowledge search hits must be a list.")
    return [KnowledgeSearchHit.model_validate(item) for item in payload]
