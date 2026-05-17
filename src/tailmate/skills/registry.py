"""Canonical skill registry and discovery pipeline."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from importlib import import_module
from pkgutil import iter_modules
from types import ModuleType
from typing import Any

from tailmate.agent_runtime.pipeline.skill import Skill as RuntimeSkill
from tailmate.contracts.errors import SkillRegistrationError
from tailmate.skills.base import Skill
from tailmate.skills.definition import SkillDefinition


SKILL_MANIFEST_ATTRIBUTE = "SKILL_DEFINITION"


@dataclass(frozen=True)
class DiscoveredSkillDefinition:
    """Loaded skill definition together with its source module."""

    definition: SkillDefinition
    source_module: str


@dataclass(frozen=True)
class SkillRegistryEntry:
    """Registry inventory record for both enabled and disabled skills."""

    skill_id: str
    name: str
    description: str
    input_contract: str
    output_contract: str
    adapter_dependencies: tuple[str, ...]
    source_module: str
    enabled: bool
    reason: str | None = None
    skill: Skill | None = None


@dataclass
class InMemorySkillRegistry:
    """Single registration point for all attachable skills."""

    _entries: dict[str, SkillRegistryEntry] = field(default_factory=dict)
    _runtime_skills: dict[str, RuntimeSkill] = field(default_factory=dict)

    def register(
        self,
        skill: Skill,
        *,
        definition: SkillDefinition | None = None,
        source_module: str = "",
        enabled: bool = True,
        reason: str | None = None,
    ) -> None:
        definition = definition or SkillDefinition(
            skill_id=skill.spec.skill_id,
            name=skill.spec.skill_id,
            description=skill.spec.description,
            input_contract="unknown",
            output_contract="unknown",
            factory=lambda _dependencies: skill,
        )
        self._entries[skill.spec.skill_id] = SkillRegistryEntry(
            skill_id=definition.skill_id,
            name=definition.name,
            description=definition.description,
            input_contract=definition.input_contract,
            output_contract=definition.output_contract,
            adapter_dependencies=definition.adapter_dependencies,
            source_module=source_module,
            enabled=enabled,
            reason=reason,
            skill=skill,
        )

    def register_definition(
        self,
        definition: SkillDefinition,
        *,
        source_module: str,
        enabled: bool,
        reason: str | None = None,
        skill: Skill | None = None,
    ) -> None:
        self._entries[definition.skill_id] = SkillRegistryEntry(
            skill_id=definition.skill_id,
            name=definition.name,
            description=definition.description,
            input_contract=definition.input_contract,
            output_contract=definition.output_contract,
            adapter_dependencies=definition.adapter_dependencies,
            source_module=source_module,
            enabled=enabled,
            reason=reason,
            skill=skill,
        )

    def all(self) -> list[Skill]:
        return [
            entry.skill
            for entry in self.entries()
            if entry.enabled and entry.skill is not None
        ]

    def register_runtime_skill(self, skill: RuntimeSkill) -> None:
        """Register one runtime skill for orchestration-step lookups."""

        self._runtime_skills[skill.skill_id] = skill

    def skills(self) -> list[RuntimeSkill]:
        """Return all registered runtime skills in a stable order."""

        return [self._runtime_skills[skill_id] for skill_id in sorted(self._runtime_skills)]

    def get_skill(self, skill_id: str) -> RuntimeSkill:
        """Resolve one runtime skill by identifier."""

        try:
            return self._runtime_skills[skill_id]
        except KeyError as exc:
            raise SkillRegistrationError(
                f"Runtime skill '{skill_id}' is not registered."
            ) from exc

    def entries(self) -> list[SkillRegistryEntry]:
        return [self._entries[skill_id] for skill_id in sorted(self._entries)]


def discover_skill_definitions(package_name: str = "tailmate.skills") -> list[DiscoveredSkillDefinition]:
    """Auto-discover all skill definitions exported from skill packages."""

    package = import_module(package_name)
    package_paths = getattr(package, "__path__", None)
    if package_paths is None:
        return []

    discovered: list[DiscoveredSkillDefinition] = []
    for module_info in sorted(iter_modules(package_paths), key=lambda item: item.name):
        if not module_info.ispkg or module_info.name.startswith("_"):
            continue
        module = _load_skill_module(package_name, module_info.name)
        definition = getattr(module, SKILL_MANIFEST_ATTRIBUTE, None)
        if not isinstance(definition, SkillDefinition):
            continue
        discovered.append(
            DiscoveredSkillDefinition(definition=definition, source_module=module.__name__)
        )
    return discovered


def register_skill_definitions(
    registry: InMemorySkillRegistry,
    *,
    definitions: Iterable[DiscoveredSkillDefinition],
    dependency_resolver: Callable[[str], Any | None],
    enabled_skill_ids: set[str] | None = None,
    disabled_skill_ids: set[str] | None = None,
) -> InMemorySkillRegistry:
    """Materialize discovered skill definitions into the active registry."""

    enabled_skill_ids = enabled_skill_ids or set()
    disabled_skill_ids = disabled_skill_ids or set()
    for discovered in definitions:
        definition = discovered.definition
        enabled, reason = evaluate_skill_flag_state(
            definition,
            enabled_skill_ids=enabled_skill_ids,
            disabled_skill_ids=disabled_skill_ids,
        )
        if not enabled:
            registry.register_definition(
                definition,
                source_module=discovered.source_module,
                enabled=False,
                reason=reason,
            )
            continue

        resolved_dependencies: dict[str, Any] = {}
        missing_dependencies: list[str] = []
        for dependency_name in definition.adapter_dependencies:
            dependency = dependency_resolver(dependency_name)
            if dependency is None:
                missing_dependencies.append(dependency_name)
            else:
                resolved_dependencies[dependency_name] = dependency

        if missing_dependencies:
            registry.register_definition(
                definition,
                source_module=discovered.source_module,
                enabled=False,
                reason=(
                    "Missing adapter dependencies: " + ", ".join(sorted(missing_dependencies))
                ),
            )
            continue

        skill = definition.factory(resolved_dependencies)
        registry.register(
            skill,
            definition=definition,
            source_module=discovered.source_module,
            enabled=True,
        )

    return registry


def register_discovered_skills(
    registry: InMemorySkillRegistry,
    *,
    dependency_resolver: Callable[[str], Any | None],
    enabled_skill_ids: set[str] | None = None,
    disabled_skill_ids: set[str] | None = None,
) -> InMemorySkillRegistry:
    """Discover and register all skill packages under `tailmate.skills`."""

    return register_skill_definitions(
        registry,
        definitions=discover_skill_definitions(),
        dependency_resolver=dependency_resolver,
        enabled_skill_ids=enabled_skill_ids,
        disabled_skill_ids=disabled_skill_ids,
    )


def register_builtin_skills(
    registry: InMemorySkillRegistry,
    *,
    sanitized_media_store: Any | None = None,
    dog_profile_db_adapter: Any | None = None,
    profile_extractor: Any | None = None,
    enabled_skill_ids: set[str] | None = None,
    disabled_skill_ids: set[str] | None = None,
) -> InMemorySkillRegistry:
    """Backward-compatible helper for tests that do not build a full container."""

    dependencies = {
        "sanitized_media_store": sanitized_media_store,
        "dog_profile_db_adapter": dog_profile_db_adapter,
        "profile_extractor": profile_extractor,
    }
    return register_discovered_skills(
        registry,
        dependency_resolver=dependencies.get,
        enabled_skill_ids=enabled_skill_ids,
        disabled_skill_ids=disabled_skill_ids,
    )


def evaluate_skill_flag_state(
    definition: SkillDefinition,
    *,
    enabled_skill_ids: set[str],
    disabled_skill_ids: set[str],
) -> tuple[bool, str | None]:
    """Resolve the enabled/disabled state for one skill definition."""

    if definition.skill_id in disabled_skill_ids:
        return False, "Disabled by TAILMATE_DISABLED_SKILLS."
    if enabled_skill_ids:
        if definition.skill_id in enabled_skill_ids:
            return True, None
        return False, "Not selected by TAILMATE_ENABLED_SKILLS."
    if not definition.default_enabled:
        return False, "Disabled by default."
    return True, None


def _load_skill_module(package_name: str, skill_name: str) -> ModuleType:
    """Resolve a skill package manifest with a manifest-module preference."""

    manifest_module_name = f"{package_name}.{skill_name}.manifest"
    try:
        return import_module(manifest_module_name)
    except ModuleNotFoundError as exc:
        if exc.name != manifest_module_name:
            raise
    return import_module(f"{package_name}.{skill_name}")
