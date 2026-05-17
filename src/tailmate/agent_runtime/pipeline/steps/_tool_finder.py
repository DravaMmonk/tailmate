"""Shared helper for locating a tool by name across registered skills."""

from __future__ import annotations

from tailmate.agent_runtime.ports.skill_registry import SkillRegistry


def find_tool(registry: SkillRegistry, tool_name: str):
    """Return the first tool whose name matches ``tool_name``, or ``None``."""
    for skill in registry.all():
        for tool in skill.tools:
            if tool.name == tool_name:
                return tool
    return None
