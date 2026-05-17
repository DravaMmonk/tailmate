"""Scaffold generation for new skills."""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from textwrap import dedent


SKILL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class SkillScaffoldContext:
    """Derived naming context for a generated skill scaffold."""

    skill_id: str
    package_name: str
    class_name: str
    tool_class_name: str
    adapter_class_name: str
    request_type_name: str
    result_type_name: str
    tool_id: str
    adapter_builder_name: str


def create_new_skill_scaffold(skill_name: str, *, cwd: Path | None = None) -> list[Path]:
    """Create the standard contract, adapter, skill, docs, and test skeleton."""

    context = build_skill_scaffold_context(skill_name)
    repo_root = find_repo_root(cwd or Path.cwd())
    files = render_scaffold_files(repo_root, context)
    created: list[Path] = []
    for path, content in files:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite existing scaffold file: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)
    return created


def render_new_skill_next_steps(context: SkillScaffoldContext) -> str:
    """Render the required follow-up checklist for a scaffolded skill."""

    return dedent(
        f"""\
        Next steps for {context.skill_id}:
          1. Define the intent string in src/tailmate/agent_runtime/intent_classifier/intents.py
          2. Add a routing rule in RuleBasedIntentClassifier or update the LLM classifier prompt
          3. Map the intent to the skill in the root-agent dispatch path
          4. Register the adapter dependency in the container and manifest
          5. Replace the generated TODO_FIELD placeholders in the contract, adapter, and slice doc
          6. Update CHANGELOG.md and the relevant controlled documents before opening a PR
          7. Run: uv run python -m pytest tests/unit/test_{context.package_name}_skill.py
        """
    ).rstrip()


def build_skill_scaffold_context(skill_name: str) -> SkillScaffoldContext:
    """Validate and normalize the requested skill name."""

    normalized = skill_name.strip()
    if not SKILL_NAME_PATTERN.fullmatch(normalized):
        raise ValueError("Skill names must be snake_case and start with a letter.")
    class_name = "".join(part.capitalize() for part in normalized.split("_"))
    return SkillScaffoldContext(
        skill_id=normalized,
        package_name=normalized,
        class_name=class_name,
        tool_class_name=f"{class_name}Tool",
        adapter_class_name=f"{class_name}Adapter",
        request_type_name=f"{class_name}Request",
        result_type_name=f"{class_name}Result",
        tool_id=f"{normalized}.run",
        adapter_builder_name=f"build_{normalized}_adapter",
    )


def find_repo_root(start: Path) -> Path:
    """Find the repository root for the current workspace."""

    for candidate in [start, *start.parents]:
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "tailmate").is_dir():
            return candidate
    raise RuntimeError("Could not find the Tailmate repository root from the current working dir.")


def render_scaffold_files(
    repo_root: Path,
    context: SkillScaffoldContext,
) -> list[tuple[Path, str]]:
    """Render all scaffold files for one new skill."""

    return [
        (
            repo_root / "src" / "tailmate" / "contracts" / f"{context.package_name}.py",
            render_contract_template(context),
        ),
        (
            repo_root / "src" / "tailmate" / "adapters" / context.package_name / "__init__.py",
            render_adapter_init_template(context),
        ),
        (
            repo_root / "src" / "tailmate" / "adapters" / context.package_name / "stub.py",
            render_adapter_template(context),
        ),
        (
            repo_root / "src" / "tailmate" / "skills" / context.package_name / "__init__.py",
            render_skill_init_template(context),
        ),
        (
            repo_root / "src" / "tailmate" / "skills" / context.package_name / "skill.py",
            render_skill_template(context),
        ),
        (
            repo_root / "src" / "tailmate" / "skills" / context.package_name / "manifest.py",
            render_manifest_template(context),
        ),
        (
            repo_root / "tests" / "unit" / f"test_{context.package_name}_skill.py",
            render_unit_test_template(context),
        ),
        (
            repo_root / "tests" / "integration" / f"test_{context.package_name}_orchestration.py",
            render_integration_test_template(context),
        ),
        (
            repo_root / "tests" / "contract" / f"test_{context.package_name}_registration.py",
            render_contract_test_template(context),
        ),
        (
            repo_root / "docs" / f"{context.package_name}-slice.md",
            render_slice_doc_template(context),
        ),
    ]


def render_contract_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        """Contracts for the {context.skill_id} skill."""

        from __future__ import annotations

        from collections.abc import Mapping
        from typing import Any, TypedDict


        class {context.request_type_name}(TypedDict):
            """Input contract for {context.skill_id}."""

            TODO_FIELD: str


        class {context.result_type_name}(TypedDict):
            """Output contract for {context.skill_id}."""

            status: str


        def normalize_{context.skill_id}_request(payload: Mapping[str, Any]) -> {context.request_type_name}:
            """Validate the request payload for {context.skill_id}."""

            value = str(payload.get("TODO_FIELD", "")).strip()
            if not value:
                raise ValueError("TODO_FIELD is required.")
            return {{"TODO_FIELD": value}}
        '''
    )


def render_adapter_init_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        """Adapters for the {context.skill_id} slice."""

        from tailmate.adapters.{context.package_name}.stub import {context.adapter_class_name}

        __all__ = ["{context.adapter_class_name}"]
        '''
    )


def render_adapter_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        """Adapter stub for the {context.skill_id} slice."""

        from __future__ import annotations

        from dataclasses import dataclass


        @dataclass
        class {context.adapter_class_name}:
            """Replace this stub with the real adapter boundary for {context.skill_id}."""

            def run(self, payload: dict[str, str]) -> dict[str, str]:
                return {{
                    "status": "stub",
                    "echo": payload["TODO_FIELD"],
                }}
        '''
    )


def render_skill_init_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        """{context.skill_id} skill package."""

        from tailmate.skills.{context.package_name}.manifest import SKILL_DEFINITION
        from tailmate.skills.{context.package_name}.skill import build_{context.skill_id}_skill

        __all__ = ["SKILL_DEFINITION", "build_{context.skill_id}_skill"]
        '''
    )


def render_skill_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        """Skill implementation for {context.skill_id}."""

        from __future__ import annotations

        from dataclasses import dataclass
        from typing import Any

        from tailmate.agent_runtime.models.skill_spec import SkillSpec
        from tailmate.adapters.{context.package_name}.stub import {context.adapter_class_name}
        from tailmate.contracts.{context.package_name} import normalize_{context.skill_id}_request
        from tailmate.contracts.errors import DomainError
        from tailmate.skills.base import Skill


        @dataclass
        class {context.tool_class_name}:
            """Placeholder tool for {context.skill_id} until business logic is implemented."""

            adapter: {context.adapter_class_name}
            name: str = "{context.tool_id}"

            def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
                try:
                    request = normalize_{context.skill_id}_request(payload)
                except Exception as exc:
                    raise DomainError("Invalid {context.skill_id} payload.") from exc
                return self.adapter.run(request)


        def build_{context.skill_id}_skill(
            *,
            adapter: {context.adapter_class_name},
        ) -> Skill:
            """Build the scaffolded {context.skill_id} skill."""

            tool = {context.tool_class_name}(adapter=adapter)
            return Skill(
                spec=SkillSpec(
                    skill_id="{context.skill_id}",
                    description="TODO: replace the scaffold description for {context.skill_id}.",
                    tool_ids=[tool.name],
                ),
                tools=[tool],
            )
        '''
    )


def render_manifest_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        """Manifest for the {context.skill_id} skill."""

        from __future__ import annotations

        from collections.abc import Mapping
        from typing import Any

        from tailmate.adapters.{context.package_name}.stub import {context.adapter_class_name}
        from tailmate.skills.base import Skill
        from tailmate.skills.definition import SkillDefinition
        from tailmate.skills.{context.package_name}.skill import build_{context.skill_id}_skill


        def build_from_dependencies(dependencies: Mapping[str, Any]) -> Skill:
            """Build the {context.skill_id} skill from resolved adapters."""

            adapter = dependencies["{context.package_name}_adapter"]
            if not isinstance(adapter, {context.adapter_class_name}):
                raise TypeError(
                    "{context.skill_id} requires a {context.adapter_class_name} dependency."
                )
            return build_{context.skill_id}_skill(adapter=adapter)


        SKILL_DEFINITION = SkillDefinition(
            skill_id="{context.skill_id}",
            name="{context.skill_id}",
            description="TODO: replace the scaffold description for {context.skill_id}.",
            input_contract="tailmate.contracts.{context.package_name}.{context.request_type_name}",
            output_contract="tailmate.contracts.{context.package_name}.{context.result_type_name}",
            adapter_dependencies=("{context.package_name}_adapter",),
            factory=build_from_dependencies,
            default_enabled=False,
        )
        '''
    )


def render_unit_test_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        from __future__ import annotations

        from tailmate.adapters.{context.package_name}.stub import {context.adapter_class_name}
        from tailmate.skills.{context.package_name}.skill import {context.tool_class_name}


        class Fake{context.adapter_class_name}({context.adapter_class_name}):
            def __init__(self) -> None:
                self.calls: list[dict[str, str]] = []

            def run(self, payload: dict[str, str]) -> dict[str, str]:
                self.calls.append(payload)
                return {{"status": "ok"}}


        def test_{context.skill_id}_tool_invokes_adapter_with_normalized_payload() -> None:
            adapter = Fake{context.adapter_class_name}()
            tool = {context.tool_class_name}(adapter=adapter)
            payload = tool.invoke({{"TODO_FIELD": "value"}})

            assert adapter.calls == [{{"TODO_FIELD": "value"}}]
            assert payload == {{"status": "ok"}}


        # Next test to add: validation failures for missing or malformed request fields.
        # Next test to add: adapter failures mapped into the expected domain error contract.
        '''
    )


def render_integration_test_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        from __future__ import annotations

        from tailmate.skills.registry import InMemorySkillRegistry, register_discovered_skills


        def test_{context.skill_id}_skill_is_discovered_but_disabled_by_default() -> None:
            registry = register_discovered_skills(
                InMemorySkillRegistry(),
                dependency_resolver=lambda _name: None,
            )

            entry = next(item for item in registry.entries() if item.skill_id == "{context.skill_id}")
            assert entry.enabled is False
            assert entry.reason == "Disabled by default."
        '''
    )


def render_contract_test_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        from __future__ import annotations

        from tailmate.skills.registry import discover_skill_definitions


        def test_{context.skill_id}_manifest_is_discoverable() -> None:
            discovered = {{
                item.definition.skill_id: item
                for item in discover_skill_definitions()
            }}

            entry = discovered["{context.skill_id}"]
            assert entry.definition.input_contract == (
                "tailmate.contracts.{context.package_name}.{context.request_type_name}"
            )
            assert entry.definition.output_contract == (
                "tailmate.contracts.{context.package_name}.{context.result_type_name}"
            )
        '''
    )


def render_slice_doc_template(context: SkillScaffoldContext) -> str:
    return dedent(
        f'''\
        # {context.skill_id} Slice

        This document is a controlled feature record for the `{context.skill_id}` slice.

        ## Cognition

        - TODO: describe prompt and reasoning changes.

        ## Action

        - TODO: describe the skill, tool, and adapter behavior.

        ## Memory

        - TODO: describe persistence or state changes.

        ## Vertical Slice Checklist

        - Contract: `src/tailmate/contracts/{context.package_name}.py`
        - Adapter: `src/tailmate/adapters/{context.package_name}/stub.py`
        - Skill: `src/tailmate/skills/{context.package_name}/`
        - Orchestration: TODO
        - Tests: `tests/unit/test_{context.package_name}_skill.py`, `tests/integration/test_{context.package_name}_orchestration.py`, `tests/contract/test_{context.package_name}_registration.py`
        '''
    )
