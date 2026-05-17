from __future__ import annotations

import importlib.util
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SMOKE_TEST_PATH = PROJECT_ROOT / "deployment" / "agent_engine" / "smoke_test.py"


def load_smoke_test_module():
    spec = importlib.util.spec_from_file_location(
        "deployment_agent_engine_smoke_test",
        SMOKE_TEST_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_test_includes_optional_user_id(set_env_values, monkeypatch, capsys) -> None:
    module = load_smoke_test_module()
    captured: dict[str, object] = {}

    class FakeRemoteAgent:
        def query(self, *, input):
            captured["input"] = input
            return {"status": "ok", "echo": input}

    class FakeAgentEngines:
        def get(self, *, name: str):
            captured["resource_name"] = name
            return FakeRemoteAgent()

    class FakeClient:
        def __init__(self, *, project: str, location: str):
            captured["project"] = project
            captured["location"] = location
            self.agent_engines = FakeAgentEngines()

    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module.vertexai, "Client", FakeClient)
    set_env_values(
        {
            "TAILMATE_PROJECT_ID": "tailmate",
            "TAILMATE_LOCATION": "us-central1",
            "TAILMATE_AGENT_ENGINE_RESOURCE_NAME": (
                "projects/1/locations/us-central1/reasoningEngines/test-engine"
            ),
            "TAILMATE_SMOKE_SESSION_ID": "smoke-session",
            "TAILMATE_SMOKE_MESSAGE": "My dog is Peanut.",
            "TAILMATE_SMOKE_DOG_ID": "dog-1",
            "TAILMATE_SMOKE_USER_ID": "user-1",
        }
    )

    module.main()

    response = json.loads(capsys.readouterr().out)
    assert captured["project"] == "tailmate"
    assert captured["location"] == "us-central1"
    assert captured["resource_name"] == (
        "projects/1/locations/us-central1/reasoningEngines/test-engine"
    )
    assert captured["input"] == {
        "session_id": "smoke-session",
        "message": "My dog is Peanut.",
        "metadata": {
            "dog_id": "dog-1",
            "user_id": "user-1",
        },
    }
    assert response["status"] == "ok"
