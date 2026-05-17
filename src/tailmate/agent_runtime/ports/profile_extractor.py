"""Business port for dog profile extraction strategies."""

from __future__ import annotations

from typing import Protocol

from tailmate.contracts.dog_profile import DogProfile, ExtractionResult


class ProfileExtractor(Protocol):
    """Extract structured dog profile updates from a free-form user message."""

    strategy_name: str

    def extract(self, user_message: str, current_profile: DogProfile) -> ExtractionResult: ...
