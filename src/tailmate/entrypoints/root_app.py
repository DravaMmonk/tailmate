"""Module-level root agent object for source-based Agent Engine deployments."""

from __future__ import annotations

import os

from tailmate.adapters.vertex_agent_engine.agent_app import create_agent_app
from tailmate.bootstrap.config import AppEnvironment

os.environ["TAILMATE_ENV"] = AppEnvironment.CLOUD.value

app = create_agent_app(environment=AppEnvironment.CLOUD)
