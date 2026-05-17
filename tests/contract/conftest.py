from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def reset_deploy_entrypoint_module() -> None:
    sys.modules.pop("tailmate.entrypoints.deploy", None)
    yield
    sys.modules.pop("tailmate.entrypoints.deploy", None)


@pytest.fixture
def set_deploy_env(set_env_values: Callable[[dict[str, Any]], None]) -> Callable[..., None]:
    defaults = {
        "TAILMATE_ENV": "LOCAL",
        "TAILMATE_PROJECT_ID": "test-project",
        "TAILMATE_LOCATION": "us-central1",
        "TAILMATE_DB_USER": "postgres",
        "TAILMATE_DB_PASSWORD": "pw",
        "TAILMATE_DB_IP": "10.0.0.10",
        "TAILMATE_DB_NAME": "postgres",
        "TAILMATE_MEDIA_BUCKET": "tailmate-bucket",
        "TAILMATE_NETWORK_ATTACHMENT": (
            "projects/test/regions/us-central1/networkAttachments/tailmate"
        ),
    }

    def apply(**overrides: Any) -> None:
        values = dict(defaults)
        values.update(overrides)
        set_env_values(values)

    return apply
