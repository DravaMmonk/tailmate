"""Business-level media sanitization and storage contract."""

from __future__ import annotations

from typing import Protocol

from tailmate.contracts.types import StripMetadataRequest, StripMetadataResult


class SanitizedMediaStore(Protocol):
    """Strips sensitive metadata from raw media and stores the clean asset."""

    def strip_and_store(self, request: StripMetadataRequest) -> StripMetadataResult: ...
