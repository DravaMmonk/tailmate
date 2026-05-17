from __future__ import annotations

import argparse
import importlib
import io

from tailmate.contracts.constants import DOG_PROFILE_RESULT_METADATA_KEY, TURN_DEBUG_METADATA_KEY


class FakeAgent:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.queries: list[dict[str, object]] = []
        self.set_up_called = False

    def set_up(self) -> None:
        self.set_up_called = True

    def query(self, **kwargs: object) -> dict[str, object]:
        self.queries.append(kwargs)
        return self.responses.pop(0)


def test_build_parser_registers_local_chat(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.cli")

    args = module.build_parser().parse_args(
        ["local-chat", "--session-id", "chat-1", "--user-id", "user-1"]
    )

    assert args.command == "local-chat"
    assert args.session_id == "chat-1"
    assert args.user_id == "user-1"
    assert args.func.__name__ == "run_local_chat"


def test_run_local_chat_reuses_session_and_updates_dog_id(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.local_chat")
    local_config = object()
    monkeypatch.setattr(module, "ensure_local_environment", lambda: local_config)
    ensured_users: list[tuple[object, str]] = []
    monkeypatch.setattr(
        module,
        "ensure_local_user_exists",
        lambda config, user_id: ensured_users.append((config, user_id)),
    )
    fake_agent = FakeAgent(
        [
            {
                "session_id": "chat-1",
                "response": "Created a profile for Mochi.",
                "metadata": {
                    "turn_count": 2,
                    "dog_id": "dog-1",
                    DOG_PROFILE_RESULT_METADATA_KEY: {"action": "create"},
                    TURN_DEBUG_METADATA_KEY: {
                        "skill_attempted": ["dog_profile_create"],
                        "fallback_reason": None,
                    },
                },
                "error": None,
            },
            {
                "session_id": "chat-1",
                "response": "Updated Mochi's diet.",
                "metadata": {
                    "turn_count": 4,
                    "dog_id": "dog-1",
                    DOG_PROFILE_RESULT_METADATA_KEY: {"action": "enrich"},
                    TURN_DEBUG_METADATA_KEY: {
                        "skill_attempted": ["dog_profile_enrich"],
                        "fallback_reason": None,
                    },
                },
                "error": None,
            },
        ]
    )
    monkeypatch.setattr(
        module,
        "create_agent_app",
        lambda environment: fake_agent,
    )
    output = io.StringIO()
    user_inputs = iter(["Mochi is my dog", "She loves salmon", "quit"])

    exit_code = module.run_local_chat(
        argparse.Namespace(dog_id=None, session_id="chat-1", user_id="user-1", no_debug=False),
        input_func=lambda _prompt: next(user_inputs),
        output=output,
    )

    transcript = output.getvalue().splitlines()
    assert exit_code == 0
    assert fake_agent.set_up_called is True
    assert ensured_users == [(local_config, "user-1")]
    assert fake_agent.queries[0]["session_id"] == "chat-1"
    assert fake_agent.queries[0]["metadata"] == {"user_id": "user-1"}
    assert fake_agent.queries[1]["metadata"] == {"dog_id": "dog-1", "user_id": "user-1"}
    assert transcript[0] == "Session: chat-1"
    assert transcript[1] == "Created a profile for Mochi."
    assert '"dog_profile_action": "create"' in transcript[2]
    assert transcript[3] == "Updated Mochi's diet."
    assert '"dog_profile_action": "enrich"' in transcript[4]
    assert transcript[5] == "Stopping local chat."


def test_run_local_chat_hides_debug_summary_with_no_debug(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.local_chat")
    monkeypatch.setattr(module, "ensure_local_environment", lambda: object())
    monkeypatch.setattr(module, "ensure_local_user_exists", lambda config, user_id: None)
    fake_agent = FakeAgent(
        [
            {
                "session_id": "chat-1",
                "response": "Hello there.",
                "metadata": {
                    "turn_count": 2,
                    "dog_id": None,
                    TURN_DEBUG_METADATA_KEY: {
                        "skill_attempted": [],
                        "fallback_reason": "generic",
                    },
                },
                "error": None,
            }
        ]
    )
    monkeypatch.setattr(module, "create_agent_app", lambda environment: fake_agent)
    output = io.StringIO()
    user_inputs = iter(["Hi", "exit"])

    exit_code = module.run_local_chat(
        argparse.Namespace(dog_id=None, session_id="chat-1", user_id=None, no_debug=True),
        input_func=lambda _prompt: next(user_inputs),
        output=output,
    )

    transcript = output.getvalue().splitlines()
    assert exit_code == 0
    assert transcript == [
        "Session: chat-1",
        "Hello there.",
        "Stopping local chat.",
    ]


def test_run_local_chat_skips_local_user_bootstrap_without_user_id(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.local_chat")
    monkeypatch.setattr(module, "ensure_local_environment", lambda: object())
    monkeypatch.setattr(
        module,
        "ensure_local_user_exists",
        lambda config, user_id: (_ for _ in ()).throw(AssertionError("unexpected bootstrap")),
    )
    fake_agent = FakeAgent(
        [
            {
                "session_id": "chat-1",
                "response": "Hello there.",
                "metadata": {"turn_count": 2},
                "error": None,
            }
        ]
    )
    monkeypatch.setattr(module, "create_agent_app", lambda environment: fake_agent)

    exit_code = module.run_local_chat(
        argparse.Namespace(dog_id=None, session_id="chat-1", user_id=None, no_debug=True),
        input_func=lambda _prompt: "exit",
        output=io.StringIO(),
    )

    assert exit_code == 0
