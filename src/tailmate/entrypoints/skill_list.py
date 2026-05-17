"""Skill inventory entrypoint."""

from __future__ import annotations

import argparse
import json
import sys

from tailmate.entrypoints.local_env import build_local_container
from tailmate.skills.registry import SkillRegistryEntry, discover_skill_definitions


def add_skill_list_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `skill list` command."""

    parser = subparsers.add_parser(
        "list",
        help="List discovered skills with their resolved local enablement state.",
    )
    parser.set_defaults(func=run_skill_list)


def resolve_registered_tool_names(
    entry: SkillRegistryEntry,
    *,
    definition,
    container,
) -> list[str]:
    """Return the registered tool names, even for disabled skills when possible."""

    if entry.skill is not None:
        return list(entry.skill.spec.tool_ids)

    resolved_dependencies: dict[str, object] = {}
    for dependency_name in definition.adapter_dependencies:
        dependency = container.resolve_skill_dependency(dependency_name)
        if dependency is None:
            return []
        resolved_dependencies[dependency_name] = dependency

    try:
        skill = definition.factory(resolved_dependencies)
    except Exception:
        return []
    return list(skill.spec.tool_ids)


def build_skill_inventory() -> list[dict[str, object]]:
    """Build the resolved skill inventory for local developer inspection."""

    container = build_local_container()
    registry = container.build_skill_registry()
    entries = {entry.skill_id: entry for entry in registry.entries()}

    inventory: list[dict[str, object]] = []
    for discovered in discover_skill_definitions():
        definition = discovered.definition
        entry = entries[definition.skill_id]
        inventory.append(
            {
                "skill_id": definition.skill_id,
                "default_enabled": definition.default_enabled,
                "enabled": entry.enabled,
                "reason": entry.reason,
                "tool_names": resolve_registered_tool_names(
                    entry,
                    definition=definition,
                    container=container,
                ),
            }
        )
    return inventory


def run_skill_list(args: argparse.Namespace) -> int:
    """Print the resolved local skill inventory as JSON."""

    del args
    json.dump(build_skill_inventory(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0
