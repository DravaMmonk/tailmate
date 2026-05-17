"""Abstract media/blob storage contract."""

from __future__ import annotations

from typing import Protocol


class BlobStore(Protocol):
    """Stores and resolves binary assets such as video and images."""

    def put(self, logical_path: str, content_type: str, payload: bytes) -> str: ...

    def resolve_resource(self, logical_path: str) -> str: ...

    def delete(self, logical_path: str) -> None: ...
