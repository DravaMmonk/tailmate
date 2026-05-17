#!/usr/bin/env python3
"""Sync the deployment requirements file from the uv lockfile."""

from __future__ import annotations

from pathlib import Path
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "deployment" / "agent_engine" / "requirements.txt"
DEPLOYMENT_PYTHON_VERSION = "3.11"


def build_uv_export_command() -> list[str]:
    return [
        "uv",
        "export",
        "--format",
        "requirements.txt",
        "--frozen",
        "--no-dev",
        "--no-editable",
        "--no-emit-project",
        "--no-header",
        "--no-hashes",
        "--python",
        DEPLOYMENT_PYTHON_VERSION,
        "--output-file",
        str(REQUIREMENTS_PATH),
    ]


def main() -> None:
    subprocess.run(
        build_uv_export_command(),
        cwd=PROJECT_ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
