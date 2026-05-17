from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS_PATH = PROJECT_ROOT / "deployment" / "agent_engine" / "requirements.txt"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_agent_engine_requirements.py"


def load_sync_module():
    spec = importlib.util.spec_from_file_location(
        "sync_agent_engine_requirements",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agent_engine_requirements_are_lockfile_exported() -> None:
    command = load_sync_module().build_uv_export_command()
    result = subprocess.run(
        command[:-1] + ["-"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    expected = result.stdout.strip().splitlines()
    actual = REQUIREMENTS_PATH.read_text(encoding="utf-8").strip().splitlines()

    assert actual == expected
