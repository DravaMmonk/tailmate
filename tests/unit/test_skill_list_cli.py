from __future__ import annotations

import importlib

from tailmate.agent_runtime.models.skill_spec import SkillSpec
from tailmate.skills.base import Skill
from tailmate.skills.definition import SkillDefinition
from tailmate.skills.registry import DiscoveredSkillDefinition, SkillRegistryEntry


class FakeContainer:
    def __init__(self, entries: list[SkillRegistryEntry], dependencies: dict[str, object]) -> None:
        self._entries = entries
        self._dependencies = dependencies

    def build_skill_registry(self):
        class Registry:
            def __init__(self, entries: list[SkillRegistryEntry]) -> None:
                self._entries = entries

            def entries(self) -> list[SkillRegistryEntry]:
                return list(self._entries)

        return Registry(self._entries)

    def resolve_skill_dependency(self, dependency_name: str):
        return self._dependencies.get(dependency_name)


def build_skill(skill_id: str, tool_ids: list[str]) -> Skill:
    return Skill(spec=SkillSpec(skill_id=skill_id, description=skill_id, tool_ids=tool_ids))


def test_build_parser_registers_skill_list(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.cli")

    args = module.build_parser().parse_args(["skill", "list"])

    assert args.command == "skill"
    assert args.skill_command == "list"
    assert args.func.__name__ == "run_skill_list"


def test_build_skill_inventory_combines_default_enabled_and_tool_names(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.skill_list")

    enabled_definition = SkillDefinition(
        skill_id="dog_profile",
        name="Dog Profile",
        description="Dog profile skill",
        input_contract="input",
        output_contract="output",
        adapter_dependencies=(),
        default_enabled=True,
        factory=lambda _dependencies: build_skill("dog_profile", ["dog_profile_create"]),
    )
    disabled_definition = SkillDefinition(
        skill_id="strip_metadata",
        name="Strip Metadata",
        description="Strip metadata skill",
        input_contract="input",
        output_contract="output",
        adapter_dependencies=("sanitized_media_store",),
        default_enabled=False,
        factory=lambda dependencies: build_skill(
            "strip_metadata",
            [f"strip_{'ok' if 'sanitized_media_store' in dependencies else 'missing'}"],
        ),
    )
    discovered = [
        DiscoveredSkillDefinition(
            definition=enabled_definition,
            source_module="tailmate.skills.dog_profile.manifest",
        ),
        DiscoveredSkillDefinition(
            definition=disabled_definition,
            source_module="tailmate.skills.strip_metadata.manifest",
        ),
    ]
    container = FakeContainer(
        entries=[
            SkillRegistryEntry(
                skill_id="dog_profile",
                name="Dog Profile",
                description="Dog profile skill",
                input_contract="input",
                output_contract="output",
                adapter_dependencies=(),
                source_module="tailmate.skills.dog_profile.manifest",
                enabled=True,
                reason=None,
                skill=build_skill("dog_profile", ["dog_profile_create"]),
            ),
            SkillRegistryEntry(
                skill_id="strip_metadata",
                name="Strip Metadata",
                description="Strip metadata skill",
                input_contract="input",
                output_contract="output",
                adapter_dependencies=("sanitized_media_store",),
                source_module="tailmate.skills.strip_metadata.manifest",
                enabled=False,
                reason="Disabled by default.",
                skill=None,
            ),
        ],
        dependencies={"sanitized_media_store": object()},
    )
    monkeypatch.setattr(module, "build_local_container", lambda: container)
    monkeypatch.setattr(module, "discover_skill_definitions", lambda: discovered)

    inventory = module.build_skill_inventory()

    assert inventory == [
        {
            "skill_id": "dog_profile",
            "default_enabled": True,
            "enabled": True,
            "reason": None,
            "tool_names": ["dog_profile_create"],
        },
        {
            "skill_id": "strip_metadata",
            "default_enabled": False,
            "enabled": False,
            "reason": "Disabled by default.",
            "tool_names": ["strip_ok"],
        },
    ]


def test_run_skill_list_prints_json(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.skill_list")
    monkeypatch.setattr(
        module,
        "build_skill_inventory",
        lambda: [
            {
                "skill_id": "dog_profile",
                "default_enabled": True,
                "enabled": True,
                "reason": None,
                "tool_names": ["dog_profile_create"],
            }
        ],
    )

    exit_code = module.run_skill_list(args=None)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"skill_id": "dog_profile"' in captured.out
    assert '"tool_names": [' in captured.out
