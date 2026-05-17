from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

import pytest

from tailmate.contracts.constants import STRIP_METADATA_REQUEST_METADATA_KEY
from tailmate.entrypoints.local_demo import (
    DEFAULT_STRIP_METADATA_MESSAGE,
    build_local_demo_query,
)


def test_build_local_demo_query_with_message_only() -> None:
    args = argparse.Namespace(
        message="hello",
        file=None,
        dog_id=None,
        user_id=None,
        session_id="session-1",
        resource_kind=None,
        content_type=None,
    )

    payload = build_local_demo_query(args)

    assert payload == {
        "session_id": "session-1",
        "message": "hello",
        "metadata": {},
    }


def test_build_local_demo_query_with_file_defaults_message(tmp_path: Path) -> None:
    media_path = tmp_path / "sample.jpg"
    media_path.write_bytes(b"sample-bytes")
    args = argparse.Namespace(
        message="",
        file=str(media_path),
        dog_id="dog-2",
        user_id=None,
        session_id="session-2",
        resource_kind=None,
        content_type=None,
    )

    payload = build_local_demo_query(args)
    request = payload["metadata"][STRIP_METADATA_REQUEST_METADATA_KEY]

    assert payload["session_id"] == "session-2"
    assert payload["message"] == DEFAULT_STRIP_METADATA_MESSAGE
    assert payload["metadata"]["dog_id"] == "dog-2"
    assert request["resource_kind"] == "images"
    assert request["filename"] == "sample.jpg"
    assert request["content_type"] == "image/jpeg"


def test_build_local_demo_query_infers_audio_resource_kind(tmp_path: Path) -> None:
    media_path = tmp_path / "voice.mp3"
    media_path.write_bytes(b"audio-bytes")
    args = argparse.Namespace(
        message="",
        file=str(media_path),
        dog_id="dog-audio",
        user_id=None,
        session_id="session-audio",
        resource_kind=None,
        content_type=None,
    )

    payload = build_local_demo_query(args)

    assert payload["metadata"][STRIP_METADATA_REQUEST_METADATA_KEY]["resource_kind"] == "audio"


def test_build_local_demo_query_requires_input() -> None:
    args = argparse.Namespace(
        message="",
        file=None,
        dog_id=None,
        user_id=None,
        session_id=None,
        resource_kind=None,
        content_type=None,
    )

    with pytest.raises(ValueError, match="--message or --file"):
        build_local_demo_query(args)


def test_build_local_demo_query_requires_dog_id_for_file(tmp_path: Path) -> None:
    media_path = tmp_path / "sample.jpg"
    media_path.write_bytes(b"sample-bytes")
    args = argparse.Namespace(
        message="",
        file=str(media_path),
        dog_id=None,
        user_id=None,
        session_id="session-3",
        resource_kind=None,
        content_type=None,
    )

    with pytest.raises(ValueError, match="--dog-id is required when --file is provided"):
        build_local_demo_query(args)


def test_build_local_demo_query_includes_user_id_when_provided() -> None:
    args = argparse.Namespace(
        message="hello",
        file=None,
        dog_id="dog-4",
        user_id="user-4",
        session_id="session-4",
        resource_kind=None,
        content_type=None,
    )

    payload = build_local_demo_query(args)

    assert payload == {
        "session_id": "session-4",
        "message": "hello",
        "metadata": {"dog_id": "dog-4", "user_id": "user-4"},
    }


def test_run_local_demo_bootstraps_local_user_when_provided(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.local_demo")
    local_config = object()
    monkeypatch.setattr(
        importlib.import_module("tailmate.entrypoints.local_env"),
        "ensure_local_environment",
        lambda: local_config,
    )
    ensured_users: list[tuple[object, str]] = []
    monkeypatch.setattr(
        importlib.import_module("tailmate.entrypoints.local_env"),
        "ensure_local_user_exists",
        lambda config, user_id: ensured_users.append((config, user_id)),
    )

    class FakeAgent:
        def __init__(self) -> None:
            self.set_up_called = False
            self.payloads: list[dict[str, object]] = []

        def set_up(self) -> None:
            self.set_up_called = True

        def query(self, **kwargs: object) -> dict[str, object]:
            self.payloads.append(kwargs)
            return {"response": "ok"}

    fake_agent = FakeAgent()
    monkeypatch.setattr(module, "create_agent_app", lambda environment: fake_agent)

    exit_code = module.run_local_demo(
        argparse.Namespace(
            message="hello",
            file=None,
            dog_id=None,
            user_id="user-4",
            session_id="session-4",
            resource_kind=None,
            content_type=None,
        )
    )

    assert exit_code == 0
    assert ensured_users == [(local_config, "user-4")]
    assert fake_agent.set_up_called is True
    assert fake_agent.payloads == [
        {"session_id": "session-4", "message": "hello", "metadata": {"user_id": "user-4"}}
    ]


def test_run_local_demo_skips_local_user_bootstrap_without_user_id(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.local_demo")
    monkeypatch.setattr(
        importlib.import_module("tailmate.entrypoints.local_env"),
        "ensure_local_environment",
        lambda: object(),
    )
    monkeypatch.setattr(
        importlib.import_module("tailmate.entrypoints.local_env"),
        "ensure_local_user_exists",
        lambda config, user_id: (_ for _ in ()).throw(AssertionError("unexpected bootstrap")),
    )

    class FakeAgent:
        def set_up(self) -> None:
            return None

        def query(self, **kwargs: object) -> dict[str, object]:
            return {"response": "ok", "metadata": kwargs["metadata"]}

    monkeypatch.setattr(module, "create_agent_app", lambda environment: FakeAgent())

    exit_code = module.run_local_demo(
        argparse.Namespace(
            message="hello",
            file=None,
            dog_id=None,
            user_id=None,
            session_id="session-4",
            resource_kind=None,
            content_type=None,
        )
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {"response": "ok", "metadata": {}}
