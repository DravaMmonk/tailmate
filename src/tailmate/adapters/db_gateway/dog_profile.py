"""Dog profile persistence adapter backed by the Cloud Run gateway."""

from __future__ import annotations

from dataclasses import dataclass

from tailmate.adapters.db_gateway.client import DbGatewayClient
from tailmate.agent_runtime.current_context import get_current_context
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.contracts.dog_profile import (
    CreateDogProfileInput,
    CreateDogProfileOutput,
    DogProfile,
    EnrichDogProfileInput,
    EnrichDogProfileOutput,
    ExtractionResult,
    normalize_create_dog_profile_output,
    normalize_dog_profile,
    normalize_enrich_dog_profile_output,
)


@dataclass
class GatewayDogProfileDBAdapter(DogProfileDBAdapter):
    """Persist dog profile operations through the Cloud Run gateway."""

    client: DbGatewayClient

    @staticmethod
    def _current_session_id() -> str | None:
        context = get_current_context()
        if context is None:
            return None
        session_id = context.session_id.strip()
        return session_id or None

    def create_profile(self, request: CreateDogProfileInput) -> CreateDogProfileOutput:
        payload = self.client.create_dog_profile(
            request.model_dump(mode="json", exclude_none=True)
        )
        return normalize_create_dog_profile_output(payload)

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None:
        payload = self.client.load_dog_profile(
            dog_id,
            trusted_user_id=requesting_user_id,
            session_id=self._current_session_id(),
        )
        if payload is None:
            return None
        return normalize_dog_profile(payload)

    def list_profiles(self, *, requesting_user_id: str) -> list[DogProfile]:
        payload = self.client.list_dog_profiles(trusted_user_id=requesting_user_id)
        return [normalize_dog_profile(profile) for profile in payload]

    def enrich_profile(
        self,
        request: EnrichDogProfileInput,
        extraction_result: ExtractionResult,
    ) -> EnrichDogProfileOutput:
        payload = self.client.enrich_dog_profile(
            request.dog_id,
            {
                "user_message": request.user_message,
                "current_profile": (
                    request.current_profile.model_dump(mode="json")
                    if request.current_profile is not None
                    else None
                ),
                "extraction_result": extraction_result.model_dump(mode="json"),
            },
            trusted_user_id=request.requesting_user_id,
            session_id=self._current_session_id(),
        )
        return normalize_enrich_dog_profile_output(payload)
