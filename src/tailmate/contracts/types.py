"""Shared typed payloads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, NotRequired, TypedDict, cast

from pydantic import BaseModel, ConfigDict

from werkzeug.utils import secure_filename

from tailmate.contracts.constants import STRIP_METADATA_REQUEST_METADATA_KEY

MediaKind = Literal["image", "video", "audio"]

ResponseProvenance = Literal[
    "kb_verified",
    "llm_with_kb_scope",
    "llm_generated",
    "deterministic",
]

MAX_QUERY_MESSAGE_LENGTH = 4000
DEFAULT_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_AUDIO_UPLOAD_BYTES = 25 * 1024 * 1024
DEFAULT_VIDEO_UPLOAD_BYTES = 50 * 1024 * 1024


class PublicModel(BaseModel):
    """Base model for caller-facing payloads that must ignore future fields."""

    model_config = ConfigDict(extra="ignore")


class PublicAgentQueryRequest(PublicModel):
    """Public `/v1/agent/query` request envelope."""

    message: Any = ""
    session_id: Any | None = None
    dog_id: Any | None = None
    strip_metadata_request: Mapping[str, Any] | None = None


class PublicPlatformConnectionRequest(PublicModel):
    """Public `/v1/users/connections/<platform>` request envelope."""

    platform_user_id: Any = ""
    status: Any | None = None


class ErrorDetail(TypedDict):
    """Structured error payload returned to callers."""

    code: int
    type: str
    message: str


class QueryInput(TypedDict):
    """Serializable input contract for agent queries."""

    session_id: str
    message: str
    metadata: NotRequired[dict[str, Any]]


class QueryOutput(TypedDict):
    """Serializable output contract for agent queries."""

    session_id: str
    response: str
    metadata: dict[str, Any]
    error: ErrorDetail | None


class PublicAgentQueryInput(TypedDict):
    """Serializable public gateway input contract for authenticated agent queries."""

    message: str
    session_id: NotRequired[str]
    dog_id: NotRequired[str]
    strip_metadata_request: NotRequired[StripMetadataRequest]


class StripMetadataRequest(TypedDict):
    """Serializable input contract for media privacy sanitization."""

    dog_id: str
    resource_kind: str
    filename: str
    content_type: str
    payload_base64: str
    session_id: NotRequired[str]


class StripMetadataResult(TypedDict):
    """Serializable output contract for sanitized media storage."""

    media_id: str
    dog_id: str
    resource_kind: str
    logical_path: str
    media_ref: str
    resource_uri: str
    filename: str
    content_type: str
    media_kind: MediaKind
    sanitization_method: str
    sanitization_status: str
    bytes_stored: int
    metadata_stripped: bool
    session_id: str | None
    transcription_text: str | None
    transcription_model: str | None


class PlatformConnectionInput(TypedDict):
    """Serializable input contract for account platform connection writes."""

    platform_user_id: str
    status: NotRequired[str]


class BridgeQueryInput(TypedDict):
    """Serializable input contract for IAM-protected bridge agent queries."""

    platform: str
    platform_user_id: str
    message: str
    session_id: NotRequired[str]
    dog_id: NotRequired[str]


class BridgePlatformUserInput(TypedDict):
    """Serializable input contract for bridge-side platform-user auto-provisioning."""

    platform: str
    platform_user_id: str


def normalize_query_message(message: Any, *, field_name: str = "message") -> str:
    """Normalize and bound query text before it reaches the runtime."""

    normalized = str(message).strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    if len(normalized) > MAX_QUERY_MESSAGE_LENGTH:
        raise ValueError(
            f"{field_name} must be at most {MAX_QUERY_MESSAGE_LENGTH} characters."
        )
    return normalized


def normalize_upload_filename(filename: Any) -> str:
    """Return a safe upload filename that cannot inject path segments."""

    normalized = secure_filename(str(filename).strip())
    if not normalized:
        raise ValueError("Strip metadata filename must not be empty.")
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def resolve_media_upload_limit(
    content_type: str,
    *,
    max_upload_bytes: int | None = None,
) -> int:
    """Resolve the maximum allowed upload size for a media payload."""

    normalized_content_type = str(content_type).split(";", maxsplit=1)[0].strip().lower()
    if normalized_content_type.startswith("image/"):
        limit = DEFAULT_IMAGE_UPLOAD_BYTES
    elif normalized_content_type.startswith("audio/"):
        limit = DEFAULT_AUDIO_UPLOAD_BYTES
    else:
        limit = DEFAULT_VIDEO_UPLOAD_BYTES
    if max_upload_bytes is not None:
        limit = min(limit, max_upload_bytes)
    if limit <= 0:
        raise ValueError("Upload size limits must be greater than zero.")
    return limit


def normalize_query_input(
    input: QueryInput | None = None,
    **kwargs: Any,
) -> QueryInput:
    """Accept both local `input={...}` calls and Agent Engine flattened kwargs."""

    payload: dict[str, Any] = {}
    if input is not None:
        payload.update(input)
    payload.update(kwargs)

    missing = [key for key in ("session_id", "message") if key not in payload]
    if missing:
        raise ValueError(f"Missing required query input fields: {', '.join(missing)}")

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, Mapping):
        raise ValueError("QueryInput.metadata must be a mapping when provided.")

    return {
        "session_id": str(payload["session_id"]),
        "message": normalize_query_message(payload["message"]),
        "metadata": dict(metadata),
    }


def normalize_public_agent_query_input(payload: Mapping[str, Any]) -> PublicAgentQueryInput:
    """Validate the public gateway query payload before it is mapped to QueryInput."""

    envelope = PublicAgentQueryRequest.model_validate(dict(payload))
    message = normalize_query_message(envelope.message)

    normalized: PublicAgentQueryInput = {
        "message": message,
    }

    raw_session_id = envelope.session_id
    if raw_session_id is not None:
        session_id = str(raw_session_id).strip()
        if not session_id:
            raise ValueError("session_id must not be empty when provided.")
        normalized["session_id"] = session_id

    raw_dog_id = envelope.dog_id
    if raw_dog_id is not None:
        dog_id = str(raw_dog_id).strip()
        if not dog_id:
            raise ValueError("dog_id must not be empty when provided.")
        normalized["dog_id"] = dog_id

    raw_strip_request = envelope.strip_metadata_request
    if raw_strip_request is not None:
        if not isinstance(raw_strip_request, Mapping):
            raise ValueError(
                f"{STRIP_METADATA_REQUEST_METADATA_KEY} must be an object when provided."
            )
        normalized["strip_metadata_request"] = normalize_strip_metadata_request(raw_strip_request)

    return normalized


def normalize_platform_connection_input(payload: Mapping[str, Any]) -> PlatformConnectionInput:
    """Validate a platform-connection write request."""

    envelope = PublicPlatformConnectionRequest.model_validate(dict(payload))
    platform_user_id = str(envelope.platform_user_id).strip()
    if not platform_user_id:
        raise ValueError("platform_user_id is required.")

    normalized: PlatformConnectionInput = {"platform_user_id": platform_user_id}
    raw_status = envelope.status
    if raw_status is not None:
        status = str(raw_status).strip()
        if not status:
            raise ValueError("status must not be empty when provided.")
        normalized["status"] = status
    return normalized


def normalize_bridge_query_input(payload: Mapping[str, Any]) -> BridgeQueryInput:
    """Validate the IAM bridge query payload before it is mapped to QueryInput."""

    normalized_user = normalize_bridge_platform_user_input(payload)
    message = normalize_query_message(payload.get("message", ""))

    normalized: BridgeQueryInput = {
        "platform": normalized_user["platform"],
        "platform_user_id": normalized_user["platform_user_id"],
        "message": message,
    }

    raw_session_id = payload.get("session_id")
    if raw_session_id is not None:
        session_id = str(raw_session_id).strip()
        if not session_id:
            raise ValueError("session_id must not be empty when provided.")
        normalized["session_id"] = session_id

    raw_dog_id = payload.get("dog_id")
    if raw_dog_id is not None:
        dog_id = str(raw_dog_id).strip()
        if not dog_id:
            raise ValueError("dog_id must not be empty when provided.")
        normalized["dog_id"] = dog_id

    return normalized


def normalize_bridge_platform_user_input(payload: Mapping[str, Any]) -> BridgePlatformUserInput:
    """Validate the bridge auto-provision payload for non-web platform identities."""

    platform = str(payload.get("platform", "")).strip()
    if not platform:
        raise ValueError("platform is required.")

    platform_user_id = str(payload.get("platform_user_id", "")).strip()
    if not platform_user_id:
        raise ValueError("platform_user_id is required.")

    return {
        "platform": platform,
        "platform_user_id": platform_user_id,
    }


def normalize_strip_metadata_request(payload: Mapping[str, Any]) -> StripMetadataRequest:
    """Validate the shared media-sanitization request payload."""

    missing = [
        key
        for key in ("dog_id", "resource_kind", "filename", "content_type", "payload_base64")
        if key not in payload
    ]
    if missing:
        raise ValueError(f"Missing required strip metadata fields: {', '.join(missing)}")

    normalized: StripMetadataRequest = {
        "dog_id": str(payload["dog_id"]).strip(),
        "resource_kind": str(payload["resource_kind"]).strip(),
        "filename": normalize_upload_filename(payload["filename"]),
        "content_type": str(payload["content_type"]).strip(),
        "payload_base64": str(payload["payload_base64"]).strip(),
    }
    if "session_id" in payload and payload["session_id"] is not None:
        normalized["session_id"] = str(payload["session_id"]).strip()
    for key, value in normalized.items():
        if not value:
            raise ValueError(f"Strip metadata field '{key}' cannot be empty.")
    return normalized


def normalize_strip_metadata_result(payload: Mapping[str, Any]) -> StripMetadataResult:
    """Validate the shared media-sanitization result payload."""

    missing = [
        key
        for key in (
            "media_id",
            "dog_id",
            "resource_kind",
            "logical_path",
            "media_ref",
            "resource_uri",
            "filename",
            "content_type",
            "media_kind",
            "sanitization_method",
            "sanitization_status",
            "bytes_stored",
            "metadata_stripped",
            "session_id",
        )
        if key not in payload
    ]
    if missing:
        raise ValueError(f"Missing required strip metadata result fields: {', '.join(missing)}")

    media_kind = _normalize_media_kind(payload["media_kind"])

    bytes_stored = payload["bytes_stored"]
    if not isinstance(bytes_stored, int):
        raise ValueError("Strip metadata result bytes_stored must be an integer.")

    metadata_stripped = payload["metadata_stripped"]
    if not isinstance(metadata_stripped, bool):
        raise ValueError("Strip metadata result metadata_stripped must be a boolean.")

    return {
        "media_id": str(payload["media_id"]).strip(),
        "dog_id": str(payload["dog_id"]).strip(),
        "resource_kind": str(payload["resource_kind"]).strip(),
        "logical_path": str(payload["logical_path"]).strip(),
        "media_ref": str(payload["media_ref"]).strip(),
        "resource_uri": str(payload["resource_uri"]).strip(),
        "filename": str(payload["filename"]).strip(),
        "content_type": str(payload["content_type"]).strip(),
        "media_kind": media_kind,
        "sanitization_method": str(payload["sanitization_method"]).strip(),
        "sanitization_status": str(payload["sanitization_status"]).strip(),
        "bytes_stored": bytes_stored,
        "metadata_stripped": metadata_stripped,
        "session_id": None if payload["session_id"] is None else str(payload["session_id"]).strip(),
        "transcription_text": _normalize_optional_text(payload.get("transcription_text")),
        "transcription_model": _normalize_optional_text(payload.get("transcription_model")),
    }


def extract_strip_metadata_request(metadata: Mapping[str, Any]) -> StripMetadataRequest | None:
    """Return the media-sanitization request from query metadata when present."""

    raw_request = metadata.get(STRIP_METADATA_REQUEST_METADATA_KEY)
    if raw_request is None:
        return None
    if not isinstance(raw_request, Mapping):
        raise ValueError(
            f"Query metadata field '{STRIP_METADATA_REQUEST_METADATA_KEY}' must be an object."
        )
    return normalize_strip_metadata_request(raw_request)


def _normalize_media_kind(value: Any) -> MediaKind:
    normalized = str(value).strip().lower()
    if normalized not in {"image", "video", "audio"}:
        raise ValueError("Strip metadata result media_kind must be 'image', 'video', or 'audio'.")
    return cast(MediaKind, normalized)
