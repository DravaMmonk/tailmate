from __future__ import annotations

import sys

import pytest


ENTRYPOINT_MODULES = (
    "tailmate.entrypoints.cli",
    "tailmate.entrypoints.env_check",
    "tailmate.entrypoints.local_chat",
    "tailmate.entrypoints.local_demo",
    "tailmate.entrypoints.local_dev",
    "tailmate.entrypoints.local_env",
    "tailmate.entrypoints.session_delete",
    "tailmate.entrypoints.session_inspect",
    "tailmate.entrypoints.skill_list",
)


@pytest.fixture(autouse=True)
def skip_local_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAILMATE_SKIP_LOCAL_BOOTSTRAP", "1")


@pytest.fixture(autouse=True)
def reset_entrypoint_modules() -> None:
    yield
    for module_name in ENTRYPOINT_MODULES:
        sys.modules.pop(module_name, None)
