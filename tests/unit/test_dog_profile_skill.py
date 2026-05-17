from __future__ import annotations

from datetime import datetime, timezone

from tailmate.adapters.dog_profile.db_adapter import apply_extraction_result
from tailmate.contracts.dog_profile import (
    CreateDogProfileOutput,
    DogProfile,
    EnrichDogProfileOutput,
    ExtractionResult,
)
from tailmate.skills.dog_profile.skill import CreateDogProfileTool, EnrichDogProfileTool


class FakeDogProfileDBAdapter:
    def __init__(self) -> None:
        self.created_name: str | None = None
        self.created_user_id: str | None = None
        self.loaded_profile_request: tuple[str, str] | None = None
        self.last_enrich_request = None
        self.last_extraction_result = None
        self.profile = DogProfile(
            dog_id="dog-1",
            user_id="user-1",
            name="DouDou",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def create_profile(self, request):
        self.created_name = request.name
        self.created_user_id = request.user_id
        return CreateDogProfileOutput(
            dog_id="dog-1",
            profile_summary="DouDou",
            created_at=datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc),
        )

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None:
        self.loaded_profile_request = (dog_id, requesting_user_id)
        return self.profile

    def enrich_profile(self, request, extraction_result):
        self.last_enrich_request = request
        self.last_extraction_result = extraction_result
        return EnrichDogProfileOutput(
            updated_fields={"breed": "Corgi"},
            raw_note=None,
            extraction_strategy_used=extraction_result.strategy_used,
        )


class FakeExtractor:
    strategy_name = "rule"

    def extract(self, user_message: str, current_profile: DogProfile) -> ExtractionResult:
        assert current_profile.dog_id == "dog-1"
        return ExtractionResult(
            structured_fields={"breed": "Corgi"},
            raw_note=None,
            confidence=0.9,
            strategy_used="rule",
        )


def test_create_dog_profile_tool_returns_json_payload() -> None:
    adapter = FakeDogProfileDBAdapter()

    payload = CreateDogProfileTool(dog_profile_db_adapter=adapter).invoke(
        {"name": "DouDou", "session_id": "session-1", "user_id": "user-1"}
    )

    assert adapter.created_name == "DouDou"
    assert adapter.created_user_id == "user-1"
    assert payload["dog_id"] == "dog-1"
    assert payload["profile_summary"] == "DouDou"


def test_enrich_dog_profile_tool_loads_profile_before_extracting() -> None:
    adapter = FakeDogProfileDBAdapter()
    tool = EnrichDogProfileTool(
        dog_profile_db_adapter=adapter,
        profile_extractor=FakeExtractor(),
    )

    payload = tool.invoke(
        {
            "dog_id": "dog-1",
            "requesting_user_id": "user-1",
            "user_message": "DouDou is a corgi",
        }
    )

    assert adapter.loaded_profile_request == ("dog-1", "user-1")
    assert adapter.last_extraction_result.strategy_used == "rule"
    assert payload["updated_fields"]["breed"] == "Corgi"


def test_apply_extraction_result_merges_lists_and_raw_note() -> None:
    current_profile = DogProfile(
        dog_id="dog-1",
        name="DouDou",
        medical_history=["knee surgery"],
        raw_notes=["Afraid of vacuum cleaners."],
    )
    extraction_result = ExtractionResult(
        structured_fields={"medical_history": ["seasonal allergy", "knee surgery"]},
        raw_note="Walks twice a day.",
        confidence=0.88,
        strategy_used="rule",
    )

    mutation = apply_extraction_result(current_profile, extraction_result)

    assert mutation.touched is True
    assert mutation.updated_fields["medical_history"] == [
        "knee surgery",
        "seasonal allergy",
    ]
    assert mutation.stored_raw_note == "Walks twice a day."
    assert mutation.updated_profile.raw_notes == [
        "Afraid of vacuum cleaners.",
        "Walks twice a day.",
    ]
