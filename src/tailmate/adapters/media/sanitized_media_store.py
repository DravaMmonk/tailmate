"""Direct media sanitization adapter used in the local sandbox."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import io
import logging
from pathlib import Path
import subprocess  # nosec B404
import tempfile
from uuid import uuid4

from PIL import Image, ImageOps

from tailmate.adapters.database.media_asset_store import DatabaseMediaAssetStore, MediaAssetRecord
from tailmate.adapters.localfs.blob_store import validate_logical_path
from tailmate.agent_runtime.current_context import get_current_context, get_current_user_id
from tailmate.agent_runtime.ports.audio_transcriber import AudioTranscriber
from tailmate.agent_runtime.ports.blob_store import BlobStore
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.contracts.errors import (
    AuthorizationError,
    DomainError,
    MediaAssetPersistenceError,
    MediaProcessingError,
    UnsupportedMediaTypeError,
)
from tailmate.contracts.types import StripMetadataRequest, StripMetadataResult


logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "TIFF"}
ALLOWED_RESOURCE_KINDS = frozenset({"images", "videos", "audio"})
DEFAULT_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
    "audio/aac": ".aac",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}


def decode_payload(payload_base64: str) -> bytes:
    """Decode a base64 media payload or raise a domain-level validation error."""

    try:
        return base64.b64decode(payload_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DomainError("strip_metadata payload_base64 must be valid base64 data.") from exc


def normalize_filename(filename: str) -> str:
    """Strip any directory segments from an uploaded filename."""

    normalized = Path(filename).name.strip()
    if not normalized:
        raise DomainError("strip_metadata filename must not be empty.")
    return normalized


def normalize_resource_kind(resource_kind: str) -> str:
    """Normalize the caller-provided storage segment."""

    normalized = resource_kind.strip().lower()
    if not normalized:
        raise DomainError("strip_metadata resource_kind must not be empty.")
    if normalized not in ALLOWED_RESOURCE_KINDS:
        raise DomainError("strip_metadata resource_kind must be one of: images, videos, audio.")
    return normalized


def classify_media_kind(content_type: str) -> str:
    """Map a MIME type to the supported media-processing branch."""

    content_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    if content_type.startswith("video/"):
        return "video"
    raise UnsupportedMediaTypeError(content_type)


def resolve_file_extension(filename: str, content_type: str) -> str:
    """Resolve the stored file extension from the upload metadata."""

    suffix = Path(filename).suffix.lower()
    if suffix:
        return suffix
    return DEFAULT_EXTENSION_BY_CONTENT_TYPE.get(content_type.split(";", maxsplit=1)[0].strip().lower(), ".bin")


def build_logical_path(
    *,
    dog_id: str,
    resource_kind: str,
    media_id: str,
    filename: str,
    content_type: str,
) -> tuple[str, str]:
    """Return the normalized filename and logical blob path."""

    normalized_filename = normalize_filename(filename)
    normalized_resource_kind = normalize_resource_kind(resource_kind)
    stored_filename = f"{media_id}{resolve_file_extension(normalized_filename, content_type)}"
    logical_path = validate_logical_path(
        f"dogs/{dog_id.strip()}/{normalized_resource_kind}/{stored_filename}"
    )
    return normalized_filename, logical_path


def resolve_session_id(request: StripMetadataRequest) -> str | None:
    """Return the explicit or request-scoped session id for media tracking."""

    explicit_session_id = request.get("session_id")
    if explicit_session_id:
        return explicit_session_id
    current_context = get_current_context()
    if current_context is None:
        return None
    return current_context.session_id


def strip_image_metadata(payload: bytes) -> bytes:
    """Rewrite an image from raw pixels so EXIF and other metadata are dropped."""

    try:
        with Image.open(io.BytesIO(payload)) as image:
            normalized = ImageOps.exif_transpose(image)
            normalized.load()
            image_format = (image.format or "").upper()
            if image_format not in SUPPORTED_IMAGE_FORMATS:
                raise UnsupportedMediaTypeError(image.get_format_mimetype() or "image/unknown")

            clean_image = Image.frombytes(normalized.mode, normalized.size, normalized.tobytes())
            if image_format == "JPEG" and clean_image.mode not in {"RGB", "L"}:
                clean_image = clean_image.convert("RGB")

            buffer = io.BytesIO()
            clean_image.save(buffer, format=image_format)
            return buffer.getvalue()
    except UnsupportedMediaTypeError:
        raise
    except Exception as exc:
        raise MediaProcessingError("Failed to strip image metadata.") from exc


def _strip_ffmpeg_metadata(
    payload: bytes,
    *,
    filename: str,
    ffmpeg_binary: str,
    error_label: str,
) -> bytes:
    """Use ffmpeg to copy streams while dropping container metadata."""

    suffix = Path(filename).suffix or ".bin"
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / f"input{suffix}"
            output_path = Path(temp_dir) / f"output{suffix}"
            input_path.write_bytes(payload)
            command = [
                ffmpeg_binary,
                "-y",
                "-i",
                str(input_path),
                "-map_metadata",
                "-1",
                "-c",
                "copy",
                str(output_path),
            ]
            completed = subprocess.run(  # nosec B603
                command,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode != 0:
                raise MediaProcessingError(
                    f"ffmpeg failed while stripping {error_label} metadata: "
                    f"{completed.stderr.strip() or completed.stdout.strip() or 'unknown error'}"
                )
            return output_path.read_bytes()
    except FileNotFoundError as exc:
        raise MediaProcessingError(f"ffmpeg is required to strip {error_label} metadata.") from exc
    except MediaProcessingError:
        raise
    except Exception as exc:
        raise MediaProcessingError(f"Failed to strip {error_label} metadata.") from exc


def strip_video_metadata(payload: bytes, *, filename: str, ffmpeg_binary: str) -> bytes:
    """Use ffmpeg to copy the video streams while dropping container metadata."""

    return _strip_ffmpeg_metadata(
        payload,
        filename=filename,
        ffmpeg_binary=ffmpeg_binary,
        error_label="video",
    )


def strip_audio_metadata(payload: bytes, *, filename: str, ffmpeg_binary: str) -> bytes:
    """Use ffmpeg to copy the audio streams while dropping container metadata."""

    return _strip_ffmpeg_metadata(
        payload,
        filename=filename,
        ffmpeg_binary=ffmpeg_binary,
        error_label="audio",
    )


@dataclass
class DirectSanitizedMediaStore:
    """Strip metadata locally, then store only the sanitized bytes."""

    blob_store: BlobStore
    media_asset_store: DatabaseMediaAssetStore | None = None
    dog_profile_db_adapter: DogProfileDBAdapter | None = None
    audio_transcriber: AudioTranscriber | None = None
    ffmpeg_binary: str = "ffmpeg"

    def strip_and_store(self, request: StripMetadataRequest) -> StripMetadataResult:
        if self.dog_profile_db_adapter is not None:
            current_user_id = get_current_user_id()
            if not current_user_id:
                raise DomainError("Missing verified user_id for strip_metadata.")
            owned_profile = self.dog_profile_db_adapter.load_profile(
                request["dog_id"],
                requesting_user_id=current_user_id,
            )
            if owned_profile is None:
                raise AuthorizationError(
                    f"Dog profile '{request['dog_id']}' is not owned by the requesting user."
                )

        media_id = str(uuid4())
        filename, logical_path = build_logical_path(
            dog_id=request["dog_id"],
            resource_kind=request["resource_kind"],
            media_id=media_id,
            filename=request["filename"],
            content_type=request["content_type"],
        )
        normalized_content_type = request["content_type"].split(";", maxsplit=1)[0].strip().lower()
        media_kind = classify_media_kind(normalized_content_type)
        raw_payload = decode_payload(request["payload_base64"])

        transcription_text: str | None = None
        transcription_model: str | None = None
        if media_kind == "image":
            clean_payload = strip_image_metadata(raw_payload)
            sanitization_method = "pillow_reencode"
        elif media_kind == "video":
            clean_payload = strip_video_metadata(
                raw_payload,
                filename=filename,
                ffmpeg_binary=self.ffmpeg_binary,
            )
            sanitization_method = "ffmpeg_map_metadata_-1"
        else:
            clean_payload = strip_audio_metadata(
                raw_payload,
                filename=filename,
                ffmpeg_binary=self.ffmpeg_binary,
            )
            sanitization_method = "ffmpeg_map_metadata_-1"
            if self.audio_transcriber is not None:
                transcription = self.audio_transcriber.transcribe(
                    clean_payload,
                    content_type=normalized_content_type,
                )
                transcription_text = transcription.text
                transcription_model = transcription.model_name

        stored_path = self.blob_store.put(logical_path, request["content_type"], clean_payload)
        media_ref = self.blob_store.resolve_resource(stored_path)
        session_id = resolve_session_id(request)
        result: StripMetadataResult = {
            "media_id": media_id,
            "dog_id": request["dog_id"].strip(),
            "resource_kind": normalize_resource_kind(request["resource_kind"]),
            "logical_path": stored_path,
            "media_ref": media_ref,
            "resource_uri": media_ref,
            "filename": filename,
            "content_type": normalized_content_type,
            "media_kind": media_kind,
            "sanitization_method": sanitization_method,
            "sanitization_status": "sanitized",
            "bytes_stored": len(clean_payload),
            "metadata_stripped": True,
            "session_id": session_id,
            "transcription_text": transcription_text,
            "transcription_model": transcription_model,
        }
        if self.media_asset_store is None:
            return result

        try:
            self.media_asset_store.save(
                MediaAssetRecord(
                    media_id=media_id,
                    dog_id=result["dog_id"],
                    session_id=session_id,
                    resource_kind=result["resource_kind"],
                    media_kind=media_kind,
                    content_type=normalized_content_type,
                    source_filename=filename,
                    logical_path=stored_path,
                    media_ref=media_ref,
                    sanitization_method=sanitization_method,
                    sanitization_status="sanitized",
                    metadata_stripped=True,
                    byte_size=len(clean_payload),
                )
            )
        except MediaAssetPersistenceError:
            try:
                self.blob_store.delete(stored_path)
            except Exception as cleanup_error:
                logger.warning(
                    "Failed to delete sanitized media after persistence failure.",
                    exc_info=cleanup_error,
                )
            raise
        return result
