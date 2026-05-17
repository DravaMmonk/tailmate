from __future__ import annotations

from tailmate.skills.registry import discover_skill_definitions


def test_dog_profile_manifest_is_discoverable() -> None:
    discovered = {
        item.definition.skill_id: item
        for item in discover_skill_definitions()
    }

    entry = discovered["dog_profile"]
    assert entry.definition.input_contract == (
        "tailmate.contracts.dog_profile.DogProfileToolRequest"
    )
    assert entry.definition.output_contract == (
        "tailmate.contracts.dog_profile.DogProfileToolResult"
    )
    assert entry.definition.adapter_dependencies == (
        "dog_profile_db_adapter",
        "profile_extractor",
    )
    assert entry.definition.default_enabled is True
