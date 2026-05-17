from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tailmate.agent_runtime.pipeline.skill import IntentMatch
from tailmate.agent_runtime.pipeline.turn_context import SkillExecutionResult
from tailmate.contracts.constants import DOG_PROFILE_SKILL_ID, STRIP_METADATA_SKILL_ID
from tailmate.contracts.dog_profile import DogProfile, EnrichDogProfileOutput, ExtractionResult
from tailmate.contracts.errors import SkillRegistrationError
from tailmate.skills.registry import (
    InMemorySkillRegistry,
    discover_skill_definitions,
    register_skill_definitions,
)


class FakeSanitizedMediaStore:
    def strip_and_store(self, request: dict[str, str]) -> dict[str, object]:
        return {
            "media_id": "media-1",
            "dog_id": request["dog_id"],
            "resource_kind": request["resource_kind"],
            "logical_path": "dogs/dog-1/images/sample.jpg",
            "media_ref": "gs://tailmate/dogs/dog-1/images/sample.jpg",
            "resource_uri": "gs://tailmate/dogs/dog-1/images/sample.jpg",
            "filename": request["filename"],
            "content_type": request["content_type"],
            "media_kind": "image",
            "sanitization_method": "pillow_reencode",
            "sanitization_status": "sanitized",
            "bytes_stored": 123,
            "metadata_stripped": True,
            "session_id": request.get("session_id"),
        }


class FakeDogProfileDBAdapter:
    def create_profile(self, request):
        raise AssertionError("Not needed in this registry test.")

    def load_profile(self, dog_id: str, *, requesting_user_id: str) -> DogProfile | None:
        return DogProfile(
            dog_id=dog_id,
            user_id=requesting_user_id,
            name="DouDou",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def enrich_profile(self, request, extraction_result: ExtractionResult) -> EnrichDogProfileOutput:
        return EnrichDogProfileOutput(
            updated_fields={},
            raw_note=None,
            extraction_strategy_used=extraction_result.strategy_used,
        )


class FakeProfileExtractor:
    strategy_name = "rule"

    def extract(self, user_message: str, current_profile: DogProfile) -> ExtractionResult:
        return ExtractionResult(
            structured_fields={},
            raw_note=None,
            confidence=0.0,
            strategy_used="rule",
        )


class FakeRuntimeSkill:
    def __init__(self, skill_id: str, *, depends_on: tuple[str, ...] = ()) -> None:
        self.skill_id = skill_id
        self.routing_description = f"Routes {skill_id}"
        self.depends_on = depends_on

    def classify(self, ctx) -> IntentMatch | None:
        return None

    def execute(self, ctx) -> SkillExecutionResult:
        return SkillExecutionResult(skill_id=self.skill_id, outcome="noop", payload={})

    def apply_context(self, ctx, result) -> None:
        return None

    def assemble(self, ctx, result):
        return None

    def assemble_open_intent_fallback(self, ctx, result):
        return None


def build_dependencies(name: str):
    dependencies = {
        "sanitized_media_store": FakeSanitizedMediaStore(),
        "dog_profile_db_adapter": FakeDogProfileDBAdapter(),
        "profile_extractor": FakeProfileExtractor(),
    }
    return dependencies.get(name)


def test_discover_skill_definitions_loads_registered_manifests() -> None:
    discovered = {
        item.definition.skill_id: item
        for item in discover_skill_definitions()
    }

    dog_profile = discovered[DOG_PROFILE_SKILL_ID]
    strip_metadata = discovered[STRIP_METADATA_SKILL_ID]
    assert dog_profile.definition.adapter_dependencies == (
        "dog_profile_db_adapter",
        "profile_extractor",
    )
    assert strip_metadata.definition.input_contract == (
        "tailmate.contracts.types.StripMetadataRequest"
    )
    assert strip_metadata.definition.output_contract == (
        "tailmate.contracts.types.StripMetadataResult"
    )
    assert strip_metadata.definition.adapter_dependencies == ("sanitized_media_store",)


def test_register_skill_definitions_respects_disabled_flags() -> None:
    registry = register_skill_definitions(
        InMemorySkillRegistry(),
        definitions=discover_skill_definitions(),
        dependency_resolver=build_dependencies,
        disabled_skill_ids={DOG_PROFILE_SKILL_ID, STRIP_METADATA_SKILL_ID},
    )

    assert registry.all() == []
    entries = {entry.skill_id: entry for entry in registry.entries()}
    assert entries[DOG_PROFILE_SKILL_ID].reason == "Disabled by TAILMATE_DISABLED_SKILLS."
    assert entries[STRIP_METADATA_SKILL_ID].reason == "Disabled by TAILMATE_DISABLED_SKILLS."


def test_register_skill_definitions_marks_missing_dependencies_as_unavailable() -> None:
    registry = register_skill_definitions(
        InMemorySkillRegistry(),
        definitions=discover_skill_definitions(),
        dependency_resolver=lambda _name: None,
    )

    assert registry.all() == []
    entries = {entry.skill_id: entry for entry in registry.entries()}
    assert entries[DOG_PROFILE_SKILL_ID].enabled is False
    assert entries[DOG_PROFILE_SKILL_ID].reason == (
        "Missing adapter dependencies: dog_profile_db_adapter, profile_extractor"
    )
    assert entries[STRIP_METADATA_SKILL_ID].enabled is False
    assert entries[STRIP_METADATA_SKILL_ID].reason == (
        "Missing adapter dependencies: sanitized_media_store"
    )


def test_runtime_skill_registry_enumerates_registered_runtime_skills() -> None:
    registry = InMemorySkillRegistry()
    registry.register_runtime_skill(FakeRuntimeSkill("knowledge_base"))
    registry.register_runtime_skill(
        FakeRuntimeSkill("dog_profile:enrich", depends_on=("dog_profile:recall",))
    )

    skills = registry.skills()

    assert [skill.skill_id for skill in skills] == [
        "dog_profile:enrich",
        "knowledge_base",
    ]
    assert skills[0].depends_on == ("dog_profile:recall",)


def test_runtime_skill_registry_returns_runtime_skill_by_id() -> None:
    registry = InMemorySkillRegistry()
    runtime_skill = FakeRuntimeSkill("knowledge_base")
    registry.register_runtime_skill(runtime_skill)

    assert registry.get_skill("knowledge_base") is runtime_skill


def test_runtime_skill_registry_raises_for_unknown_skill_id() -> None:
    registry = InMemorySkillRegistry()

    with pytest.raises(SkillRegistrationError, match="Runtime skill 'knowledge_base' is not registered."):
        registry.get_skill("knowledge_base")
