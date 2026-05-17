"""Local development entrypoint."""

from __future__ import annotations

import os

from tailmate.adapters.vertex_agent_engine.agent_app import create_agent_app
from tailmate.agents.root.agent import RootAgent
from tailmate.bootstrap.config import AppEnvironment
from tailmate.entrypoints.local_env import (
    EnvironmentCheckResult,
    check_environment,
    collect_environment_check_results,
    ensure_local_environment,
    load_local_config,
    require_explicit_local_env_marker,
    require_local_env_file,
    strategy_requires_vertex_ai_adc,
    validate_database_proxy,
    validate_vertex_ai_adc,
)

__all__ = [
    "EnvironmentCheckResult",
    "bootstrap_local_app",
    "check_environment",
    "collect_environment_check_results",
    "ensure_local_environment",
    "load_local_config",
    "main",
    "require_explicit_local_env_marker",
    "require_local_env_file",
    "strategy_requires_vertex_ai_adc",
    "validate_database_proxy",
    "validate_vertex_ai_adc",
]


def bootstrap_local_app() -> RootAgent:
    """Creates the local agent after completing pre-flight checks."""

    ensure_local_environment()
    return create_agent_app(environment=AppEnvironment.LOCAL)


def main() -> None:
    bootstrap_local_app()
    print("Local sandbox checks passed. Agent bootstrap is ready.")


if __name__ == "__main__":
    main()
elif os.getenv("TAILMATE_SKIP_LOCAL_BOOTSTRAP") != "1":
    app = bootstrap_local_app()
