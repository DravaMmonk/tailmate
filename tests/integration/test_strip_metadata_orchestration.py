from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import tempfile

from PIL import Image

from tailmate.adapters.localfs.blob_store import LocalBlobStore
from tailmate.adapters.media.sanitized_media_store import DirectSanitizedMediaStore
from tailmate.agent_runtime.current_context import (
    RuntimeRequestContext,
    reset_current_context,
    set_current_context,
)
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.agent_runtime.services.graph_orchestrator import GraphOrchestrator
from tailmate.agent_runtime.services.rule_based_intent_classifier import RuleBasedIntentClassifier
from tailmate.contracts.constants import STRIP_METADATA_RESULT_METADATA_KEY
from tailmate.contracts.constants import TURN_DEBUG_METADATA_KEY
from tailmate.skills.registry import InMemorySkillRegistry, register_builtin_skills


class FakeSessionStore:
    def __init__(self) -> None:
        self.saved_context: SessionContext | None = None

    def load(self, session_id: str) -> SessionContext:
        return SessionContext(session_id=session_id)

    def save(self, context: SessionContext) -> None:
        self.saved_context = context


class FakeObservability:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def info(self, event_name: str, **kwargs: object) -> None:
        self.events.append((event_name, kwargs))


def build_jpeg_with_exif() -> bytes:
    image = Image.new("RGB", (8, 8), color="green")
    exif = Image.Exif()
    exif[0x010F] = "Tailmate Camera"
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_graph_orchestrator_runs_strip_metadata_skill_and_persists_result() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_store = FakeSessionStore()
        observability = FakeObservability()
        registry = register_builtin_skills(
            InMemorySkillRegistry(),
            sanitized_media_store=DirectSanitizedMediaStore(
                blob_store=LocalBlobStore(root_dir=Path(temp_dir))
            ),
        )
        orchestrator = GraphOrchestrator(
            session_store=session_store,
            skill_registry=registry,
            observability=observability,
            intent_classifier=RuleBasedIntentClassifier(registry),
        )
        token = set_current_context(
            RuntimeRequestContext(
                session_id="session-1",
                metadata={
                    "strip_metadata_request": {
                        "dog_id": "dog-1",
                        "resource_kind": "images",
                        "filename": "sample.jpg",
                        "content_type": "image/jpeg",
                        "payload_base64": base64.b64encode(build_jpeg_with_exif()).decode("utf-8"),
                    }
                },
                dog_id="dog-1",
            )
        )

        try:
            context = orchestrator.run("session-1", "store this upload safely")
        finally:
            reset_current_context(token)

        result = context.attributes[STRIP_METADATA_RESULT_METADATA_KEY]
        assert result["logical_path"].startswith("dogs/dog-1/images/")
        assert result["logical_path"].endswith(".jpg")
        assert result["session_id"] == "session-1"
        assert context.turns[-1]["role"] == "assistant"
        assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "skill:strip_metadata"
        assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "strip_metadata.success"
        assert session_store.saved_context is not None
        assert observability.events[0][0] == "orchestrator_strip_metadata"


def test_graph_orchestrator_does_not_bypass_strip_metadata_for_empty_first_message() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        session_store = FakeSessionStore()
        observability = FakeObservability()
        registry = register_builtin_skills(
            InMemorySkillRegistry(),
            sanitized_media_store=DirectSanitizedMediaStore(
                blob_store=LocalBlobStore(root_dir=Path(temp_dir))
            ),
        )
        orchestrator = GraphOrchestrator(
            session_store=session_store,
            skill_registry=registry,
            observability=observability,
            intent_classifier=RuleBasedIntentClassifier(registry),
        )
        token = set_current_context(
            RuntimeRequestContext(
                session_id="session-empty-upload",
                metadata={
                    "strip_metadata_request": {
                        "dog_id": "dog-1",
                        "resource_kind": "images",
                        "filename": "sample.jpg",
                        "content_type": "image/jpeg",
                        "payload_base64": base64.b64encode(build_jpeg_with_exif()).decode("utf-8"),
                    }
                },
                dog_id="dog-1",
            )
        )

        try:
            context = orchestrator.run("session-empty-upload", "")
        finally:
            reset_current_context(token)

        assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "skill:strip_metadata"
        assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "strip_metadata.success"
        assert context.turns[0] == {"role": "user", "message": ""}


def test_graph_orchestrator_transcribes_audio_uploads_before_routing(monkeypatch) -> None:
    class FakeAudioTranscriber:
        def transcribe(self, payload: bytes, *, content_type: str):
            assert payload == b"clean-audio"
            assert content_type == "audio/mpeg"
            return type(
                "AudioTranscription",
                (),
                {"text": "Buddy is coughing", "model_name": "gemini-2.5-flash"},
            )()

    monkeypatch.setattr(
        "tailmate.adapters.media.sanitized_media_store.strip_audio_metadata",
        lambda payload, *, filename, ffmpeg_binary: b"clean-audio",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        session_store = FakeSessionStore()
        observability = FakeObservability()
        registry = register_builtin_skills(
            InMemorySkillRegistry(),
            sanitized_media_store=DirectSanitizedMediaStore(
                blob_store=LocalBlobStore(root_dir=Path(temp_dir)),
                audio_transcriber=FakeAudioTranscriber(),
            ),
        )
        orchestrator = GraphOrchestrator(
            session_store=session_store,
            skill_registry=registry,
            observability=observability,
            intent_classifier=RuleBasedIntentClassifier(registry),
        )
        token = set_current_context(
            RuntimeRequestContext(
                session_id="session-audio",
                metadata={
                    "strip_metadata_request": {
                        "dog_id": "dog-1",
                        "resource_kind": "audio",
                        "filename": "voice.mp3",
                        "content_type": "audio/mpeg",
                        "payload_base64": base64.b64encode(b"raw-audio").decode("utf-8"),
                    }
                },
                dog_id="dog-1",
            )
        )

        try:
            context = orchestrator.run("session-audio", "Please sanitize and store this upload.")
        finally:
            reset_current_context(token)

        assert context.attributes[STRIP_METADATA_RESULT_METADATA_KEY]["media_kind"] == "audio"
        assert (
            context.attributes[STRIP_METADATA_RESULT_METADATA_KEY]["transcription_text"]
            == "Buddy is coughing"
        )
        assert context.turns[0] == {"role": "user", "message": "Buddy is coughing"}


def test_graph_orchestrator_preserves_strip_metadata_success_when_audio_transcription_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "tailmate.adapters.media.sanitized_media_store.strip_audio_metadata",
        lambda payload, *, filename, ffmpeg_binary: b"clean-audio",
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        session_store = FakeSessionStore()
        observability = FakeObservability()
        registry = register_builtin_skills(
            InMemorySkillRegistry(),
            sanitized_media_store=DirectSanitizedMediaStore(
                blob_store=LocalBlobStore(root_dir=Path(temp_dir)),
                audio_transcriber=None,
            ),
        )
        orchestrator = GraphOrchestrator(
            session_store=session_store,
            skill_registry=registry,
            observability=observability,
            intent_classifier=RuleBasedIntentClassifier(registry),
        )
        token = set_current_context(
            RuntimeRequestContext(
                session_id="session-audio-no-transcriber",
                metadata={
                    "strip_metadata_request": {
                        "dog_id": "dog-1",
                        "resource_kind": "audio",
                        "filename": "voice.mp3",
                        "content_type": "audio/mpeg",
                        "payload_base64": base64.b64encode(b"raw-audio").decode("utf-8"),
                    }
                },
                dog_id="dog-1",
            )
        )

        try:
            context = orchestrator.run(
                "session-audio-no-transcriber",
                "Please sanitize and store this upload.",
            )
            events = list(
                orchestrator.stream_run(
                    "session-audio-no-transcriber",
                    "Please sanitize and store this upload.",
                )
            )
        finally:
            reset_current_context(token)

        assert context.attributes[STRIP_METADATA_RESULT_METADATA_KEY]["media_kind"] == "audio"
        assert context.attributes[STRIP_METADATA_RESULT_METADATA_KEY]["transcription_text"] is None
        assert context.attributes[TURN_DEBUG_METADATA_KEY]["source"] == "skill:strip_metadata"
        assert context.attributes[TURN_DEBUG_METADATA_KEY]["response_key"] == "strip_metadata.success"
        assert context.turns[0] == {
            "role": "user",
            "message": "Please sanitize and store this upload.",
        }
        assert any(
            event_name == "orchestrator_audio_transcription_skipped"
            for event_name, _payload in observability.events
        )

        completed_event = events[-1]
        assert completed_event["event"] == "query.completed"
        assert completed_event["output"]["error"] is None
        assert (
            completed_event["output"]["metadata"][STRIP_METADATA_RESULT_METADATA_KEY][
                "transcription_text"
            ]
            is None
        )
        assert completed_event["output"]["response"].startswith("Sanitised media stored at ")
