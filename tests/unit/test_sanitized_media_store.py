from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
import subprocess

import pytest
from PIL import Image

from tailmate.adapters.database.media_asset_store import MediaAssetRecord
from tailmate.adapters.media.sanitized_media_store import (
    DirectSanitizedMediaStore,
    strip_audio_metadata,
    strip_video_metadata,
)
from tailmate.agent_runtime.current_context import RuntimeRequestContext, reset_current_context, set_current_context
from tailmate.contracts.errors import AuthorizationError, DomainError, MediaAssetPersistenceError


class FakeBlobStore:
    def __init__(self) -> None:
        self.payloads: dict[str, tuple[str, bytes]] = {}
        self.deleted: list[str] = []

    def put(self, logical_path: str, content_type: str, payload: bytes) -> str:
        self.payloads[logical_path] = (content_type, payload)
        return logical_path

    def resolve_resource(self, logical_path: str) -> str:
        return f"file://{logical_path}"

    def delete(self, logical_path: str) -> None:
        self.deleted.append(logical_path)
        self.payloads.pop(logical_path, None)


class FakeMediaAssetStore:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.records: list[MediaAssetRecord] = []

    def save(self, record: MediaAssetRecord) -> None:
        if self.fail:
            raise MediaAssetPersistenceError("failed to persist")
        self.records.append(record)


def build_exif_jpeg() -> bytes:
    image = Image.new("RGB", (4, 4), color="red")
    exif = Image.Exif()
    exif[271] = "TailmateCam"
    exif[272] = "Model-1"
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def test_direct_sanitized_media_store_strips_jpeg_exif_and_tracks_media_ref() -> None:
    blob_store = FakeBlobStore()
    media_asset_store = FakeMediaAssetStore()
    store = DirectSanitizedMediaStore(blob_store=blob_store, media_asset_store=media_asset_store)

    result = store.strip_and_store(
        {
            "dog_id": "dog-1",
            "resource_kind": "images",
            "filename": "photo.jpg",
            "content_type": "image/jpeg",
            "payload_base64": base64.b64encode(build_exif_jpeg()).decode("ascii"),
            "session_id": "session-1",
        }
    )

    assert result["media_ref"] == result["resource_uri"]
    assert result["sanitization_method"] == "pillow_reencode"
    stored_payload = blob_store.payloads[result["logical_path"]][1]
    with Image.open(BytesIO(stored_payload)) as sanitized:
        assert dict(sanitized.getexif()) == {}
    assert media_asset_store.records[0].media_ref == result["media_ref"]
    assert media_asset_store.records[0].session_id == "session-1"


def test_direct_sanitized_media_store_cleans_up_blob_when_tracking_fails() -> None:
    blob_store = FakeBlobStore()
    store = DirectSanitizedMediaStore(
        blob_store=blob_store,
        media_asset_store=FakeMediaAssetStore(fail=True),
    )

    with pytest.raises(MediaAssetPersistenceError, match="failed to persist"):
        store.strip_and_store(
            {
                "dog_id": "dog-1",
                "resource_kind": "images",
                "filename": "photo.jpg",
                "content_type": "image/jpeg",
                "payload_base64": base64.b64encode(build_exif_jpeg()).decode("ascii"),
            }
        )

    assert blob_store.payloads == {}
    assert len(blob_store.deleted) == 1


def test_direct_sanitized_media_store_rejects_unallowlisted_resource_kind() -> None:
    store = DirectSanitizedMediaStore(blob_store=FakeBlobStore())

    with pytest.raises(
        DomainError,
        match="strip_metadata resource_kind must be one of: images, videos, audio.",
    ):
        store.strip_and_store(
            {
                "dog_id": "dog-1",
                "resource_kind": "uploads",
                "filename": "photo.jpg",
                "content_type": "image/jpeg",
                "payload_base64": base64.b64encode(build_exif_jpeg()).decode("ascii"),
            }
        )


def test_strip_video_metadata_uses_ffmpeg_map_metadata_flag(monkeypatch, tmp_path: Path) -> None:
    del tmp_path

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool):
        assert capture_output is True
        assert text is True
        assert check is False
        assert "-map_metadata" in command
        map_index = command.index("-map_metadata")
        assert command[map_index + 1] == "-1"
        output_path = Path(command[-1])
        output_path.write_bytes(b"clean-video")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("tailmate.adapters.media.sanitized_media_store.subprocess.run", fake_run)

    assert strip_video_metadata(b"raw-video", filename="clip.mp4", ffmpeg_binary="ffmpeg") == (
        b"clean-video"
    )


def test_strip_audio_metadata_uses_ffmpeg_map_metadata_flag(monkeypatch, tmp_path: Path) -> None:
    del tmp_path

    def fake_run(command: list[str], capture_output: bool, text: bool, check: bool):
        assert capture_output is True
        assert text is True
        assert check is False
        assert "-map_metadata" in command
        map_index = command.index("-map_metadata")
        assert command[map_index + 1] == "-1"
        output_path = Path(command[-1])
        output_path.write_bytes(b"clean-audio")
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("tailmate.adapters.media.sanitized_media_store.subprocess.run", fake_run)

    assert strip_audio_metadata(b"raw-audio", filename="note.m4a", ffmpeg_binary="ffmpeg") == (
        b"clean-audio"
    )


def test_direct_sanitized_media_store_transcribes_audio_uploads(monkeypatch) -> None:
    class FakeAudioTranscriber:
        def transcribe(self, payload: bytes, *, content_type: str):
            assert payload == b"clean-audio"
            assert content_type == "audio/mpeg"
            return type(
                "AudioTranscription",
                (),
                {"text": "Buddy skipped breakfast.", "model_name": "gemini-2.5-flash"},
            )()

    monkeypatch.setattr(
        "tailmate.adapters.media.sanitized_media_store.strip_audio_metadata",
        lambda payload, *, filename, ffmpeg_binary: b"clean-audio",
    )
    store = DirectSanitizedMediaStore(
        blob_store=FakeBlobStore(),
        audio_transcriber=FakeAudioTranscriber(),
    )

    result = store.strip_and_store(
        {
            "dog_id": "dog-1",
            "resource_kind": "audio",
            "filename": "voice.mp3",
            "content_type": "audio/mpeg",
            "payload_base64": base64.b64encode(b"raw-audio").decode("ascii"),
            "session_id": "session-audio",
        }
    )

    assert result["media_kind"] == "audio"
    assert result["transcription_text"] == "Buddy skipped breakfast."
    assert result["transcription_model"] == "gemini-2.5-flash"


def test_direct_sanitized_media_store_allows_audio_without_transcriber(monkeypatch) -> None:
    monkeypatch.setattr(
        "tailmate.adapters.media.sanitized_media_store.strip_audio_metadata",
        lambda payload, *, filename, ffmpeg_binary: b"clean-audio",
    )
    store = DirectSanitizedMediaStore(blob_store=FakeBlobStore())

    result = store.strip_and_store(
        {
            "dog_id": "dog-1",
            "resource_kind": "audio",
            "filename": "voice.mp3",
            "content_type": "audio/mpeg",
            "payload_base64": base64.b64encode(b"raw-audio").decode("ascii"),
            "session_id": "session-audio",
        }
    )

    assert result["media_kind"] == "audio"
    assert result["transcription_text"] is None
    assert result["transcription_model"] is None


def test_direct_sanitized_media_store_rejects_cross_user_dog_access() -> None:
    class FakeDogProfileDBAdapter:
        def load_profile(self, dog_id: str, *, requesting_user_id: str):
            del dog_id, requesting_user_id
            raise AuthorizationError("Dog profile 'dog-1' is not owned by the requesting user.")

    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-1",
            metadata={"user_id": "user-2"},
            dog_id="dog-1",
            user_id="user-2",
        )
    )
    try:
        store = DirectSanitizedMediaStore(
            blob_store=FakeBlobStore(),
            dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        )
        with pytest.raises(AuthorizationError, match="not owned by the requesting user"):
            store.strip_and_store(
                {
                    "dog_id": "dog-1",
                    "resource_kind": "images",
                    "filename": "photo.jpg",
                    "content_type": "image/jpeg",
                    "payload_base64": base64.b64encode(build_exif_jpeg()).decode("ascii"),
                }
            )
    finally:
        reset_current_context(token)
