from __future__ import annotations

from dataclasses import dataclass

import pytest

from tailmate.agents.root.agent import RootAgent
from tailmate.contracts.constants import (
    DOG_PROFILE_RESULT_METADATA_KEY,
    KNOWLEDGE_BASE_RESULT_METADATA_KEY,
    STRIP_METADATA_REQUEST_METADATA_KEY,
    STRIP_METADATA_RESULT_METADATA_KEY,
    TURN_DEBUG_METADATA_KEY,
)
from tailmate.bootstrap.config import AppConfig
from tailmate.contracts.errors import DomainError
from tailmate.contracts.types import MAX_QUERY_MESSAGE_LENGTH, normalize_query_input


@dataclass
class FakeContext:
    session_id: str
    turns: list[dict]
    attributes: dict[str, object]


class FakeOrchestrator:
    def __init__(self, *, fail: bool = False):
        self.fail = fail

    def run(self, session_id: str, message: str) -> FakeContext:
        if self.fail:
            raise DomainError("Dog profile is incomplete.")
        return FakeContext(
            session_id=session_id,
            turns=[{"role": "user", "message": message}],
            attributes={"last_response": "Handled successfully."},
        )


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


def test_root_agent_query_returns_structured_success() -> None:
    agent = RootAgent(config=build_config())
    agent.orchestrator = FakeOrchestrator()

    response = agent.query(
        {"session_id": "session-1", "message": "hello", "metadata": {"dog_id": "dog-1"}}
    )

    assert response["session_id"] == "session-1"
    assert response["response"] == "Handled successfully."
    assert response["metadata"]["dog_id"] == "dog-1"
    assert response["error"] is None


def test_root_agent_query_wraps_tailmate_errors() -> None:
    agent = RootAgent(config=build_config())
    agent.orchestrator = FakeOrchestrator(fail=True)

    response = agent.query(
        {"session_id": "session-2", "message": "hello", "metadata": {"dog_id": "dog-2"}}
    )

    assert response["session_id"] == "session-2"
    assert response["error"] == {
        "code": 400,
        "type": "domain_error",
        "message": "Dog profile is incomplete.",
    }


def test_root_agent_query_accepts_flattened_kwargs() -> None:
    agent = RootAgent(config=build_config())
    agent.orchestrator = FakeOrchestrator()

    response = agent.query(session_id="session-3", message="hello", metadata={"dog_id": "dog-3"})

    assert response["session_id"] == "session-3"
    assert response["metadata"]["dog_id"] == "dog-3"
    assert response["error"] is None


def test_query_input_accepts_message_at_length_limit() -> None:
    payload = normalize_query_input(
        {
            "session_id": "session-4",
            "message": "x" * MAX_QUERY_MESSAGE_LENGTH,
        }
    )

    assert len(payload["message"]) == MAX_QUERY_MESSAGE_LENGTH


def test_query_input_rejects_message_over_length_limit() -> None:
    with pytest.raises(ValueError, match="at most 4000 characters"):
        normalize_query_input(
            {
                "session_id": "session-4",
                "message": "x" * (MAX_QUERY_MESSAGE_LENGTH + 1),
            }
        )


def test_root_agent_query_surfaces_strip_metadata_result() -> None:
    agent = RootAgent(config=build_config())
    agent.orchestrator = FakeOrchestrator()

    class StripMetadataOrchestrator(FakeOrchestrator):
        def run(self, session_id: str, message: str) -> FakeContext:
            return FakeContext(
                session_id=session_id,
                turns=[{"role": "user", "message": message}],
                attributes={
                    "last_response": "Sanitized media stored at gs://tailmate-media/dogs/dog-1/images/sample.jpg.",
                    STRIP_METADATA_RESULT_METADATA_KEY: {
                        "media_id": "media-1",
                        "dog_id": "dog-1",
                        "resource_kind": "images",
                        "logical_path": "dogs/dog-1/images/sample.jpg",
                        "media_ref": "gs://tailmate-media/dogs/dog-1/images/sample.jpg",
                        "resource_uri": "gs://tailmate-media/dogs/dog-1/images/sample.jpg",
                        "filename": "sample.jpg",
                        "content_type": "image/jpeg",
                        "media_kind": "image",
                        "sanitization_method": "pillow_reencode",
                        "sanitization_status": "sanitized",
                        "bytes_stored": 128,
                        "metadata_stripped": True,
                        "session_id": "session-4",
                    },
                },
            )

    agent.orchestrator = StripMetadataOrchestrator()

    response = agent.query(
        {
            "session_id": "session-4",
            "message": "sanitize this upload",
            "metadata": {
                "dog_id": "dog-1",
                STRIP_METADATA_REQUEST_METADATA_KEY: {
                    "dog_id": "dog-1",
                    "resource_kind": "images",
                    "filename": "sample.jpg",
                    "content_type": "image/jpeg",
                    "payload_base64": "c2FtcGxl",
                },
            },
        }
    )

    assert response["response"].startswith("Sanitized media stored at gs://")
    assert response["metadata"][STRIP_METADATA_RESULT_METADATA_KEY]["metadata_stripped"] is True
    assert response["metadata"][STRIP_METADATA_RESULT_METADATA_KEY]["media_ref"].startswith(
        "gs://tailmate-media/"
    )


def test_root_agent_query_surfaces_dog_profile_metadata_from_context() -> None:
    agent = RootAgent(config=build_config())

    class DogProfileOrchestrator(FakeOrchestrator):
        def run(self, session_id: str, message: str) -> FakeContext:
            return FakeContext(
                session_id=session_id,
                turns=[{"role": "user", "message": message}],
                attributes={
                    "last_response": "Created a dog profile for DouDou.",
                    "dog_id": "dog-1",
                    DOG_PROFILE_RESULT_METADATA_KEY: {
                        "action": "create",
                        "dog_id": "dog-1",
                        "profile_summary": "DouDou",
                        "created_at": "2026-03-25T00:00:00Z",
                    },
                },
            )

    agent.orchestrator = DogProfileOrchestrator()

    response = agent.query({"session_id": "session-5", "message": "my dog is called DouDou"})

    assert response["response"] == "Created a dog profile for DouDou."
    assert response["metadata"]["dog_id"] == "dog-1"
    assert response["metadata"][DOG_PROFILE_RESULT_METADATA_KEY]["action"] == "create"


def test_root_agent_query_surfaces_turn_debug_metadata() -> None:
    agent = RootAgent(config=build_config())

    class FallbackOrchestrator(FakeOrchestrator):
        def run(self, session_id: str, message: str) -> FakeContext:
            return FakeContext(
                session_id=session_id,
                turns=[{"role": "user", "message": message}],
                attributes={
                    "last_response": "Hi! I'm Tailmate's pet assistant.",
                    TURN_DEBUG_METADATA_KEY: {
                        "source": "fallback",
                        "response_key": "fallback.greeting",
                        "locale": "en-AU",
                        "locale_source": "default",
                        "requested_locale": "fr-FR",
                        "locale_fallback_reason": "unsupported_locale_defaulted_to_english",
                        "fallback_reason": "fallback.greeting",
                        "skill_attempted": [],
                        "skill_error": None,
                        "updated_fields": [],
                        "raw_note_saved": False,
                    },
                },
            )

    agent.orchestrator = FallbackOrchestrator()

    response = agent.query(
        {"session_id": "session-6", "message": "bonjour", "metadata": {"locale": "fr-FR"}}
    )

    assert response["metadata"][TURN_DEBUG_METADATA_KEY]["source"] == "fallback"
    assert (
        response["metadata"][TURN_DEBUG_METADATA_KEY]["locale_fallback_reason"]
        == "unsupported_locale_defaulted_to_english"
    )


def test_root_agent_query_does_not_surface_internal_knowledge_base_metadata() -> None:
    agent = RootAgent(config=build_config())

    class KnowledgeBaseOrchestrator(FakeOrchestrator):
        def run(self, session_id: str, message: str) -> FakeContext:
            return FakeContext(
                session_id=session_id,
                turns=[{"role": "user", "message": message}],
                attributes={
                    "last_response": "Feed adult dogs twice daily.\n\nSources: Feeding Guide",
                    KNOWLEDGE_BASE_RESULT_METADATA_KEY: {
                        "status": "hit",
                        "answer": "Feed adult dogs twice daily.",
                        "confidence": 0.91,
                        "sources": ["Feeding Guide"],
                    },
                    TURN_DEBUG_METADATA_KEY: {
                        "source": "knowledge_base",
                        "response_key": "knowledge_base.answer",
                        "locale": "en-AU",
                    },
                },
            )

    agent.orchestrator = KnowledgeBaseOrchestrator()

    response = agent.query({"session_id": "session-7", "message": "feeding help"})

    assert response["response"].startswith("Feed adult dogs twice daily.")
    assert KNOWLEDGE_BASE_RESULT_METADATA_KEY not in response["metadata"]
    assert response["metadata"][TURN_DEBUG_METADATA_KEY]["source"] == "knowledge_base"
