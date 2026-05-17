"""Vertex AI Agent Engine application boundary."""

from __future__ import annotations

import os

from tailmate.agents.root.agent import RootAgent
from tailmate.bootstrap.config import AppConfig, AppEnvironment


def create_agent_app(*, environment: AppEnvironment | None = None) -> RootAgent:
    """Creates the deployable application object."""

    if environment is not None:
        os.environ["TAILMATE_ENV"] = environment.value
    config = AppConfig.from_env()
    return RootAgent(config=config)
