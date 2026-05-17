from __future__ import annotations

from tailmate.agents.root.agent import RootAgent
from tailmate.agent_runtime.services.skill_loader import load_skill_ids
from tailmate.bootstrap.config import AppConfig
from tailmate.contracts.constants import DOG_PROFILE_SKILL_ID, STRIP_METADATA_SKILL_ID


def build_config() -> AppConfig:
    return AppConfig(
        _env_file=None,
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_ENV="LOCAL",
        TAILMATE_DB_USER="user",
        TAILMATE_DB_PASSWORD="pass",
        TAILMATE_DB_IP="10.0.0.10",
    )


def test_root_agent_setup_registers_strip_metadata_skill() -> None:
    agent = RootAgent(config=build_config())

    agent.set_up()

    assert agent.orchestrator is not None
    assert load_skill_ids(agent.orchestrator.skill_registry) == [
        DOG_PROFILE_SKILL_ID,
        STRIP_METADATA_SKILL_ID,
    ]


def test_root_agent_setup_respects_skill_feature_flags() -> None:
    agent = RootAgent(
        config=AppConfig(
            _env_file=None,
            TAILMATE_PROJECT_ID="test-project",
            TAILMATE_LOCATION="us-central1",
            TAILMATE_ENV="LOCAL",
            TAILMATE_DB_USER="user",
            TAILMATE_DB_PASSWORD="pass",
            TAILMATE_DB_IP="10.0.0.10",
            TAILMATE_DISABLED_SKILLS=f"{DOG_PROFILE_SKILL_ID},{STRIP_METADATA_SKILL_ID}",
        )
    )

    agent.set_up()

    assert agent.orchestrator is not None
    assert load_skill_ids(agent.orchestrator.skill_registry) == []
