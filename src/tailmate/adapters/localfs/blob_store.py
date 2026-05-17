"""Local filesystem implementation of the blob storage port."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tailmate.contracts.errors import AdapterError, DomainError


def validate_logical_path(logical_path: str) -> str:
    """Validate and normalize a logical resource path."""

    normalized = logical_path.strip().lstrip("/")
    parts = normalized.split("/")
    if len(parts) != 4 or parts[0] != "dogs":
        raise DomainError(
            "Logical resource paths must match 'dogs/{dog_id}/{resource_kind}/{filename}'."
        )
    if any(not part for part in parts):
        raise DomainError("Logical resource paths cannot contain empty path segments.")
    return normalized


@dataclass
class LocalBlobStore:
    """Stores media assets under a local filesystem root in LOCAL mode."""

    root_dir: Path

    def put(self, logical_path: str, content_type: str, payload: bytes) -> str:
        del content_type
        normalized = validate_logical_path(logical_path)
        destination = self.root_dir / normalized
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            destination.write_bytes(payload)
        except OSError as exc:
            raise AdapterError(f"Failed to write local blob '{normalized}'.") from exc
        return normalized

    def resolve_resource(self, logical_path: str) -> str:
        normalized = validate_logical_path(logical_path)
        return (self.root_dir / normalized).resolve().as_uri()

    def delete(self, logical_path: str) -> None:
        normalized = validate_logical_path(logical_path)
        target = self.root_dir / normalized
        try:
            if target.exists():
                target.unlink()
        except OSError as exc:
            raise AdapterError(f"Failed to delete local blob '{normalized}'.") from exc
