"""Business port for dog profile persistence."""

from __future__ import annotations

from typing import Protocol

from tailmate.contracts.dog_profile import (
    CreateDogProfileInput,
    CreateDogProfileOutput,
    DogProfile,
    EnrichDogProfileInput,
    EnrichDogProfileOutput,
    ExtractionResult,
)


class DogProfileDBAdapter(Protocol):
    """Creates, loads, and enriches dog profiles through an approved adapter."""

    def create_profile(self, request: CreateDogProfileInput) -> CreateDogProfileOutput: ...

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None: ...

    def list_profiles(self, *, requesting_user_id: str) -> list[DogProfile]: ...

    def enrich_profile(
        self,
        request: EnrichDogProfileInput,
        extraction_result: ExtractionResult,
    ) -> EnrichDogProfileOutput: ...
