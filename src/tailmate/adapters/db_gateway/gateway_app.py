"""Flask application for the Cloud Run DB and media gateway."""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass
from functools import wraps
import json
import os
from pathlib import Path
import time
from typing import Any
import google.auth
from flask import Flask, Response, current_app, g, jsonify, request, stream_with_context
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import id_token
from google.oauth2.id_token import verify_firebase_token
import pg8000
from sqlalchemy.engine import URL
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from tailmate.adapters.db_gateway.config import GatewayConfig
from tailmate.adapters.database.audit_logger import DatabaseAuditLogger
from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.db_gateway.identity import (
    DatabaseUserIdentityResolver,
    ResolvedPlatformIdentity,
    ResolvedUserAccount,
    build_internal_session_id,
    generate_external_session_id,
)
from tailmate.adapters.db_gateway.privacy import (
    UserPrivacyGatewayService,
    build_firebase_user_deleter,
)
from tailmate.adapters.db_gateway.rate_limiter import (
    DatabaseSlidingWindowRateLimiter,
    InMemorySlidingWindowRateLimiter,
    LocalFallbackSlidingWindowRateLimiter,
    SlidingWindowRateLimiter,
)
from tailmate.adapters.dog_profile.db_adapter import DatabaseDogProfileDBAdapter
from tailmate.adapters.gcs.gcs_adapter import GcsBlobStore
from tailmate.adapters.media.audio_transcriber import GeminiAudioTranscriber
from tailmate.adapters.localfs.blob_store import LocalBlobStore
from tailmate.adapters.media.sanitized_media_store import DirectSanitizedMediaStore
from tailmate.agent_runtime.ports.blob_store import BlobStore
from tailmate.agent_runtime.ports.audio_transcriber import AudioTranscriber
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.bootstrap.config import AppEnvironment
from tailmate.contracts.audit import AuditLogger
from tailmate.contracts.authz import assert_owner
from tailmate.contracts.constants import (
    PUBLIC_QUERY_PLATFORM,
    PUBLIC_AGENT_QUERY_PATH,
    PUBLIC_USER_ACTIVATE_PATH,
    PUBLIC_USER_CONNECTIONS_PATH,
    PUBLIC_USER_DELETE_PATH,
    PUBLIC_USER_EXPORT_PATH,
    PUBLIC_USER_REGISTER_PATH,
    INTERNAL_KB_CHUNK_IMPORT_PATH,
    INTERNAL_KB_CHUNK_PATH,
    INTERNAL_KB_CHUNKS_PATH,
    REQUEST_ID_HEADER,
    TRACE_ID_HEADER,
    STRIP_METADATA_REQUEST_METADATA_KEY,
    SUPPORTED_USER_CONNECTION_PLATFORMS,
    TRUSTED_USER_ID_HEADER,
)
from tailmate.contracts.dog_profile import (
    normalize_create_dog_profile_input,
    normalize_enrich_dog_profile_input,
    normalize_extraction_result,
)
from tailmate.contracts.errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    DomainError,
    TailmateError,
    InternalError,
    MediaAssetPersistenceError,
    NotFoundError,
)
from tailmate.contracts.knowledge import (
    normalize_knowledge_chunk_batch_input,
    normalize_knowledge_chunk_input,
    normalize_knowledge_chunk_preview_input,
    normalize_knowledge_search_request,
)
from tailmate.contracts.types import (
    BridgePlatformUserInput,
    BridgeQueryInput,
    PlatformConnectionInput,
    StripMetadataResult,
    resolve_media_upload_limit,
    normalize_bridge_platform_user_input,
    normalize_bridge_query_input,
    normalize_platform_connection_input,
    normalize_public_agent_query_input,
    normalize_strip_metadata_request,
)
from tailmate.observability import (
    LogContext,
    configure_structured_logging,
    generate_request_id,
    generate_trace_id,
    reset_log_context,
    set_log_context,
    update_log_context,
)
from tailmate.tracing import (
    attach_trace_context,
    configure_tracing,
    detach_trace_context,
    inject_trace_context,
    start_span,
)
from tailmate.metrics import MetricsRegistry, render_prometheus_metrics, set_metrics_registry
from tailmate.adapters.knowledge_base.management import (
    build_vertex_embedding_client,
    create_knowledge_chunk as create_knowledge_chunk_record,
    delete_knowledge_chunk as delete_knowledge_chunk_record,
    import_knowledge_chunks as import_knowledge_chunk_records,
    load_knowledge_chunk_upload_records,
    preview_knowledge_chunks as preview_knowledge_chunk_records,
    search_knowledge_chunks as search_knowledge_chunk_records,
)


DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
INTERNAL_DB_ENDPOINTS = frozenset(
    {
        "load_session",
        "save_session",
        "search_knowledge",
        "create_dog_profile",
        "list_dog_profiles",
        "load_dog_profile",
        "enrich_dog_profile",
        "upload_media",
        "ensure_bridge_platform_user",
        "claim_bridge_webhook_event",
        "bridge_query",
        "create_knowledge_chunk",
        "delete_knowledge_chunk",
        "preview_knowledge_chunks",
        "import_knowledge_chunks",
        "metrics",
    }
)
PUBLIC_BROWSER_ENDPOINT_METHODS = "DELETE, GET, OPTIONS, POST"
PUBLIC_BROWSER_ENDPOINT_HEADERS = ", ".join(
    (
        "Authorization",
        "Content-Type",
        REQUEST_ID_HEADER,
        TRACE_ID_HEADER,
    )
)


@dataclass(frozen=True)
class AuthenticatedCaller:
    """Verified caller identity extracted from the inbound ID token."""

    subject: str
    email: str | None = None

    @property
    def identity(self) -> str:
        return self.email or self.subject


def parse_allowed_origins(raw_value: str | None) -> tuple[str, ...]:
    """Parse a comma-delimited browser origin allowlist."""

    if raw_value is None:
        return ()
    return tuple(part.strip() for part in raw_value.split(",") if part.strip())


def normalize_public_app_base_url(raw_value: str) -> str:
    """Normalize the public Tailmate application base URL."""

    normalized = raw_value.strip().rstrip("/")
    if not normalized:
        raise ValueError("TAILMATE_PUBLIC_APP_BASE_URL must not be blank.")
    return normalized


def is_public_browser_path(path: str) -> bool:
    """Return whether the request path is intended for browser callers."""

    return path.startswith("/v1/")


def apply_public_cors_headers(
    response: Response,
    *,
    allowed_origins: tuple[str, ...],
    request_origin: str | None,
) -> Response:
    """Attach public browser CORS headers when the caller origin is allowlisted."""

    if "*" in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = "*"
    elif request_origin and request_origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = request_origin
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = PUBLIC_BROWSER_ENDPOINT_METHODS
    response.headers["Access-Control-Allow-Headers"] = PUBLIC_BROWSER_ENDPOINT_HEADERS
    return response


def get_db_connection(config: GatewayConfig | None = None) -> pg8000.dbapi.Connection:
    """Build the Cloud Run gateway database connection from validated settings."""

    gateway_config = config or GatewayConfig.from_env()
    return pg8000.connect(
        host=str(gateway_config.db_host),
        port=gateway_config.db_port,
        user=str(gateway_config.db_user),
        password=gateway_config.db_password_value,
        database=str(gateway_config.db_name),
        timeout=gateway_config.db_connect_timeout_seconds,
    )


def build_gateway_blob_store(config: GatewayConfig | None = None) -> BlobStore:
    """Resolve the gateway blob-store adapter from the runtime mode contract."""

    gateway_config = config or GatewayConfig.from_env()
    if gateway_config.environment is AppEnvironment.LOCAL:
        return LocalBlobStore(root_dir=Path(gateway_config.local_media_root))

    return GcsBlobStore(
        bucket_name=str(gateway_config.media_bucket),
        project_id=gateway_config.project_id,
    )


def build_gateway_database_url(config: GatewayConfig | None = None) -> str:
    """Build the direct database URL used by the gateway-side adapters."""

    gateway_config = config or GatewayConfig.from_env()
    return URL.create(
        drivername="postgresql+psycopg2",
        username=str(gateway_config.db_user),
        password=gateway_config.db_password_value,
        host=str(gateway_config.db_host),
        port=gateway_config.db_port,
        database=str(gateway_config.db_name),
    ).render_as_string(hide_password=False)


def build_gateway_engine_factory(config: GatewayConfig | None = None) -> DatabaseEngineFactory:
    """Build the shared SQLAlchemy engine factory used by gateway-side adapters."""

    gateway_config = config or GatewayConfig.from_env()
    return DatabaseEngineFactory(
        build_gateway_database_url(gateway_config),
        connect_args={
            "connect_timeout": gateway_config.db_connect_timeout_seconds,
            "application_name": "tailmate_db_gateway",
        },
    )


def build_gateway_dog_profile_db_adapter(
    config: GatewayConfig | None = None,
    *,
    audit_logger: AuditLogger | None = None,
) -> DogProfileDBAdapter:
    """Build the dog profile persistence adapter used by the gateway."""

    return DatabaseDogProfileDBAdapter(
        engine_factory=build_gateway_engine_factory(config),
        audit_logger=audit_logger,
    )


def build_gateway_user_identity_resolver(
    config: GatewayConfig | None = None,
) -> DatabaseUserIdentityResolver:
    """Build the users-table resolver used by the public identity ingress."""

    return DatabaseUserIdentityResolver(engine_factory=build_gateway_engine_factory(config))


def build_gateway_audit_logger(config: GatewayConfig | None = None) -> AuditLogger:
    """Build the audit logger used by gateway-side adapters."""

    return DatabaseAuditLogger(engine_factory=build_gateway_engine_factory(config))


def build_gateway_user_privacy_service(
    config: GatewayConfig | None = None,
    *,
    blob_store: BlobStore | None = None,
    firebase_user_deleter: Callable[[str], None] | None = None,
) -> UserPrivacyGatewayService:
    """Build the user privacy service used by the public export/delete routes."""

    gateway_config = config or GatewayConfig.from_env()
    return UserPrivacyGatewayService(
        engine_factory=build_gateway_engine_factory(gateway_config),
        blob_store=blob_store or build_gateway_blob_store(gateway_config),
        firebase_user_deleter=firebase_user_deleter or build_firebase_user_deleter(),
    )


def build_public_query_rate_limiter(
    config: GatewayConfig | None = None,
) -> SlidingWindowRateLimiter:
    """Build the public-query rate limiter for `/v1/agent/query`."""

    gateway_config = config or GatewayConfig.from_env()
    database_rate_limiter = DatabaseSlidingWindowRateLimiter(
        engine_factory=build_gateway_engine_factory(gateway_config),
        max_requests=gateway_config.public_query_rate_limit_requests,
        window_seconds=gateway_config.public_query_rate_limit_window_seconds,
    )
    if gateway_config.environment is AppEnvironment.LOCAL:
        return LocalFallbackSlidingWindowRateLimiter(
            primary=database_rate_limiter,
            fallback=InMemorySlidingWindowRateLimiter(
                max_requests=gateway_config.public_query_rate_limit_requests,
                window_seconds=gateway_config.public_query_rate_limit_window_seconds,
            ),
        )
    return database_rate_limiter


def build_knowledge_embedding_client(
    config: GatewayConfig | None = None,
) -> Any:
    """Build the Vertex embedding client used by the KB management routes."""

    gateway_config = config or GatewayConfig.from_env()
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except DefaultCredentialsError:
        credentials = None
    return build_vertex_embedding_client(
        model_name=gateway_config.embedding_model,
        project_id=gateway_config.project_id,
        location=gateway_config.location,
        credentials=credentials,
    )


def build_gateway_audio_transcriber(
    config: GatewayConfig | None = None,
) -> AudioTranscriber:
    """Build the Gemini audio transcriber used by gateway media uploads."""

    gateway_config = config or GatewayConfig.from_env()
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except DefaultCredentialsError:
        credentials = None
    return GeminiAudioTranscriber(
        model_name=gateway_config.audio_transcription_model,
        project_id=gateway_config.project_id,
        location=gateway_config.location,
        credentials=credentials,
        timeout_seconds=gateway_config.gemini_timeout_seconds,
    )


def build_firebase_token_verifier(
    config: GatewayConfig | None = None,
) -> Callable[[str], dict[str, Any]]:
    """Build the Firebase ID-token verifier used by the public agent ingress."""

    gateway_config = config or GatewayConfig.from_env()
    firebase_project_id = gateway_config.firebase_project_id

    def _verify(token: str) -> dict[str, Any]:
        try:
            claims = verify_firebase_token(
                token,
                GoogleAuthRequest(),
                audience=firebase_project_id,
            )
        except Exception as exc:
            raise AuthenticationError("Invalid Firebase ID token.") from exc
        if not isinstance(claims, dict):
            raise AuthenticationError("Invalid Firebase ID token.")
        return claims

    return _verify


def build_agent_query_handler(
    config: GatewayConfig | None = None,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build the public ingress handler that proxies requests to Agent Engine."""

    gateway_config = config or GatewayConfig.from_env()
    project_id = gateway_config.project_id
    location = gateway_config.location
    agent_resource_name = str(gateway_config.agent_engine_resource_name)

    def _query(payload: dict[str, Any]) -> dict[str, Any]:
        import vertexai

        client = vertexai.Client(project=project_id, location=location)
        remote_agent = client.agent_engines.get(name=agent_resource_name)
        response = remote_agent.query(input=payload)
        if isinstance(response, dict):
            return response
        raise RuntimeError("The Agent Engine response was not JSON-serializable.")

    return _query


def build_agent_stream_query_handler(
    config: GatewayConfig | None = None,
) -> Callable[[dict[str, Any]], Iterator[dict[str, Any]]]:
    """Build the public ingress handler that proxies streaming queries to Agent Engine."""

    gateway_config = config or GatewayConfig.from_env()
    project_id = gateway_config.project_id
    location = gateway_config.location
    agent_resource_name = str(gateway_config.agent_engine_resource_name)

    def _stream(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        import vertexai

        client = vertexai.Client(project=project_id, location=location)
        remote_agent = client.agent_engines.get(name=agent_resource_name)
        response = remote_agent.stream_query(input=payload)
        for chunk in response:
            if isinstance(chunk, dict):
                yield chunk
                continue
            raise RuntimeError("The Agent Engine streaming response was not JSON-serializable.")

    return _stream


def build_single_payload_stream_query_handler(
    query_handler: Callable[[dict[str, Any]], dict[str, Any]],
) -> Callable[[dict[str, Any]], Iterator[dict[str, Any]]]:
    """Wrap a non-streaming query handler in a one-chunk iterator."""

    def _stream(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield query_handler(payload)

    return _stream


def format_sse_event(payload: dict[str, Any], *, event: str | None = None) -> str:
    """Format a JSON payload as a single SSE event."""

    lines: list[str] = []
    event_name = event or str(payload.get("event", "message"))
    if event_name:
        lines.append(f"event: {event_name}")
    lines.append("data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n\n"


def resolve_gateway_flag(name: str, *, default: bool) -> bool:
    """Parse a boolean route-registration flag from the environment."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def normalize_json_value(value: Any, *, default: Any) -> Any:
    """Normalize pg8000 JSON/text payloads before they cross the HTTP boundary."""

    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def persist_media_asset(
    connection_factory: Callable[[], pg8000.dbapi.Connection],
    result: StripMetadataResult,
    *,
    uploaded_by: str | None = None,
) -> None:
    """Persist the sanitized media reference for downstream DB readback."""

    try:
        with closing(connection_factory()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                """
                INSERT INTO media_assets (
                    media_id,
                    dog_id,
                    session_id,
                    resource_kind,
                    media_kind,
                    content_type,
                    source_filename,
                    logical_path,
                    media_ref,
                    uploaded_by,
                    sanitization_method,
                    sanitization_status,
                    metadata_stripped,
                    byte_size
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    result["media_id"],
                    result["dog_id"],
                    result["session_id"],
                    result["resource_kind"],
                    result["media_kind"],
                    result["content_type"],
                    result["filename"],
                    result["logical_path"],
                    result["media_ref"],
                    uploaded_by,
                    result["sanitization_method"],
                    result["sanitization_status"],
                    result["metadata_stripped"],
                    result["bytes_stored"],
                ],
            )
            conn.commit()
    except Exception as exc:
        raise MediaAssetPersistenceError(
            f"Failed to persist sanitized media asset '{result['media_id']}'."
        ) from exc


def check_database_health(
    connection_factory: Callable[[], pg8000.dbapi.Connection],
) -> None:
    """Verify that the gateway can execute a trivial database round-trip."""

    with closing(connection_factory()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
    if row is None or row[0] != 1:
        raise RuntimeError("Database health probe returned an unexpected result.")


def claim_processed_webhook_event(
    connection_factory: Callable[[], pg8000.dbapi.Connection],
    *,
    message_id: str,
) -> bool:
    """Atomically claim an inbound webhook message id."""

    normalized_message_id = message_id.strip()
    if not normalized_message_id:
        raise ValueError("message_id is required.")

    with closing(connection_factory()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            INSERT INTO processed_webhook_events (message_id)
            VALUES (%s)
            ON CONFLICT DO NOTHING
            RETURNING message_id
            """,
            [normalized_message_id],
        )
        claimed_row = cursor.fetchone()
        conn.commit()
    return claimed_row is not None


def release_processed_webhook_event(
    connection_factory: Callable[[], pg8000.dbapi.Connection],
    *,
    message_id: str,
) -> bool:
    """Release a previously claimed inbound webhook message id."""

    normalized_message_id = message_id.strip()
    if not normalized_message_id:
        raise ValueError("message_id is required.")

    with closing(connection_factory()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            DELETE FROM processed_webhook_events
            WHERE message_id = %s
            RETURNING message_id
            """,
            [normalized_message_id],
        )
        released_row = cursor.fetchone()
        conn.commit()
    return released_row is not None


def parse_identity_allowlist(raw_value: str | None) -> frozenset[str]:
    """Parse a comma-separated list of caller identities."""

    if raw_value is None:
        return frozenset()
    return frozenset(
        candidate
        for candidate in (part.strip() for part in raw_value.split(","))
        if candidate
    )


def parse_boolean_env(name: str, *, default: bool) -> bool:
    """Read a strict boolean environment variable."""

    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be one of true/false, yes/no, 1/0, or on/off.")


def resolve_auth_required(explicit: bool | None, *, config: GatewayConfig | None = None) -> bool:
    """Resolve whether gateway requests must carry an app-layer bearer token."""

    if explicit is not None:
        return explicit
    if config is not None:
        return config.auth_required
    default = os.getenv("TAILMATE_ENV", "CLOUD").upper() != "LOCAL"
    return parse_boolean_env("TAILMATE_DB_GATEWAY_REQUIRE_AUTH", default=default)


def resolve_max_upload_bytes(explicit: int | None, *, config: GatewayConfig | None = None) -> int:
    """Resolve the configured maximum upload size."""

    if explicit is not None:
        max_upload_bytes = explicit
    else:
        if config is not None:
            max_upload_bytes = config.max_upload_bytes
        else:
            raw_value = (
                os.getenv("TAILMATE_DB_GATEWAY_MAX_UPLOAD_BYTES")
                or os.getenv("TAILMATE_MAX_UPLOAD_BYTES")
            )
            max_upload_bytes = int(raw_value) if raw_value else DEFAULT_MAX_UPLOAD_BYTES
    if max_upload_bytes <= 0:
        raise RuntimeError("TAILMATE_DB_GATEWAY_MAX_UPLOAD_BYTES must be greater than zero.")
    return max_upload_bytes


def verify_gateway_id_token(token: str, audience: str) -> Mapping[str, Any]:
    """Verify a Google-signed ID token for the expected Cloud Run audience."""

    return id_token.verify_oauth2_token(
        token,
        GoogleAuthRequest(),
        audience=audience,
    )


def extract_bearer_token(header_value: str | None) -> str:
    """Extract the bearer token from the Authorization header."""

    if header_value is None:
        raise AuthenticationError("Authorization bearer token is required.")
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthenticationError("Authorization bearer token is required.")
    return token.strip()


def build_authenticated_caller(claims: Mapping[str, Any]) -> AuthenticatedCaller:
    """Build a stable caller identity from verified token claims."""

    subject = str(claims.get("sub", "")).strip()
    email = str(claims.get("email", "")).strip() or None
    if not subject:
        raise AuthenticationError("Authorization token is missing the required subject claim.")
    return AuthenticatedCaller(subject=subject, email=email)


def load_session_attributes(
    connection_factory: Callable[[], pg8000.dbapi.Connection],
    session_id: str,
) -> dict[str, Any] | None:
    """Return the persisted session attributes for a session id."""

    with closing(connection_factory()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            SELECT attributes
            FROM conversation_sessions
            WHERE session_id = %s
            """,
            [session_id],
        )
        row = cursor.fetchone()
    if row is None:
        return None
    return normalize_json_value(row[0], default={})


def normalize_session_attributes(attributes: Any) -> dict[str, Any]:
    """Normalize stored session attributes into a mutable mapping."""

    if not isinstance(attributes, dict):
        return {}
    return dict(attributes)


def normalize_bound_dog_id(attributes: dict[str, Any]) -> str | None:
    """Extract the bound dog id from persisted session attributes."""

    candidate = str(attributes.get("dog_id", "")).strip()
    return candidate or None


def bind_session_to_dog(
    connection_factory: Callable[[], pg8000.dbapi.Connection],
    *,
    session_id: str,
    dog_id: str,
) -> None:
    """Bind the supplied session to a dog id, rejecting conflicting dog scopes."""

    normalized_dog_id = dog_id.strip()
    with closing(connection_factory()) as conn, closing(conn.cursor()) as cursor:
        cursor.execute(
            """
            SELECT attributes
            FROM conversation_sessions
            WHERE session_id = %s
            """,
            [session_id],
        )
        row = cursor.fetchone()

        if row is None:
            cursor.execute(
                """
                INSERT INTO conversation_sessions (session_id, turns, attributes)
                VALUES (%s, %s::jsonb, %s::jsonb)
                """,
                [session_id, json.dumps([]), json.dumps({"dog_id": normalized_dog_id})],
            )
            conn.commit()
            return

        attributes = normalize_session_attributes(normalize_json_value(row[0], default={}))
        bound_dog_id = normalize_bound_dog_id(attributes)
        if bound_dog_id and bound_dog_id != normalized_dog_id:
            raise AuthorizationError(
                f"Session '{session_id}' is not authorized to access dog '{dog_id}'."
            )
        if bound_dog_id == normalized_dog_id:
            return

        attributes["dog_id"] = normalized_dog_id
        cursor.execute(
            """
            UPDATE conversation_sessions
            SET attributes = %s::jsonb
            WHERE session_id = %s
            """,
            [json.dumps(attributes), session_id],
        )
        conn.commit()


def require_session_bound_dog(
    connection_factory: Callable[[], pg8000.dbapi.Connection],
    *,
    session_id: str,
    dog_id: str,
) -> None:
    """Require an existing session-to-dog binding for dog-scoped operations."""

    attributes = load_session_attributes(connection_factory, session_id)
    normalized_attributes = normalize_session_attributes(attributes)
    bound_dog_id = normalize_bound_dog_id(normalized_attributes)
    if bound_dog_id != dog_id.strip():
        raise AuthorizationError(
            f"Session '{session_id}' is not authorized to access dog '{dog_id}'."
        )


def merge_session_attributes(
    existing_attributes: dict[str, Any] | None,
    incoming_attributes: dict[str, Any],
) -> dict[str, Any]:
    """Preserve the bound dog id when clients persist session attributes."""

    normalized_incoming = dict(incoming_attributes)
    existing_bound_dog_id = None
    if existing_attributes is not None:
        existing_bound_dog_id = normalize_bound_dog_id(existing_attributes)
    incoming_bound_dog_id = normalize_bound_dog_id(normalized_incoming)

    if existing_bound_dog_id and incoming_bound_dog_id and incoming_bound_dog_id != existing_bound_dog_id:
        raise AuthorizationError(
            "Session attributes cannot be rebound to a different dog_id once established."
        )
    if existing_bound_dog_id:
        normalized_incoming["dog_id"] = existing_bound_dog_id
    return normalized_incoming


def cleanup_created_dog_profile(
    dog_profile_db_adapter: DogProfileDBAdapter,
    *,
    dog_id: str,
) -> None:
    """Best-effort rollback for dog profiles created before a later gateway failure."""

    delete_profile = getattr(dog_profile_db_adapter, "delete_profile", None)
    if not callable(delete_profile):
        current_app.logger.warning(
            "gateway_app could not clean up dog profile '%s' because delete_profile() is unavailable.",
            dog_id,
        )
        return
    delete_profile(dog_id)


def get_authenticated_caller() -> AuthenticatedCaller | None:
    """Return the verified caller for the current request, when present."""

    caller = getattr(g, "gateway_caller", None)
    if isinstance(caller, AuthenticatedCaller):
        return caller
    return None


def extract_firebase_uid(claims: Mapping[str, Any]) -> str:
    """Extract the canonical Firebase uid from verified token claims."""

    firebase_uid = str(
        claims.get("uid") or claims.get("user_id") or claims.get("sub") or ""
    ).strip()
    if not firebase_uid:
        raise AuthenticationError("Firebase token did not contain a uid.")
    return firebase_uid


def serialize_user_account(account: ResolvedUserAccount) -> dict[str, Any]:
    """Return a stable JSON-serializable representation of a user account."""

    return {
        "user_id": account.user_id,
        "status": account.status,
        "role": account.role,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def serialize_platform_identity(identity: ResolvedPlatformIdentity) -> dict[str, Any]:
    """Return a stable JSON-serializable representation of a platform identity."""

    return {
        "user_id": identity.user_id,
        "status": identity.status,
        "role": identity.role,
        "platform": identity.platform,
        "platform_user_id": identity.platform_user_id,
        "connection_status": identity.connection_status,
        "user_created_at": identity.user_created_at.isoformat() if identity.user_created_at else None,
        "connected_at": identity.connected_at.isoformat() if identity.connected_at else None,
        "disconnected_at": (
            identity.disconnected_at.isoformat() if identity.disconnected_at else None
        ),
    }


def normalize_connection_platform(platform: str) -> str:
    """Validate and normalize a connection platform route parameter."""

    normalized_platform = platform.strip().lower()
    if normalized_platform not in SUPPORTED_USER_CONNECTION_PLATFORMS:
        raise ValueError(
            "platform must be one of: "
            + ", ".join(sorted(SUPPORTED_USER_CONNECTION_PLATFORMS))
            + "."
        )
    return normalized_platform


def normalize_connection_status(status: str) -> str:
    """Validate and normalize a platform connection status value."""

    normalized_status = status.strip().lower()
    if normalized_status not in {"pending_verification", "active"}:
        raise ValueError(
            "status must be one of: pending_verification, active."
        )
    return normalized_status


def require_firebase_claims() -> Mapping[str, Any]:
    """Verify the Firebase bearer token on the current request."""

    token = extract_bearer_token(request.headers.get("Authorization"))
    return current_app.config["FIREBASE_TOKEN_VERIFIER"](token)


def create_app(
    *,
    blob_store: BlobStore | None = None,
    db_connection_factory: Callable[[], pg8000.dbapi.Connection] | None = None,
    dog_profile_db_adapter: DogProfileDBAdapter | None = None,
    user_identity_resolver: DatabaseUserIdentityResolver | None = None,
    user_privacy_service: UserPrivacyGatewayService | None = None,
    public_query_rate_limiter: SlidingWindowRateLimiter | None = None,
    knowledge_embedding_client: Any | None = None,
    audio_transcriber: AudioTranscriber | None = None,
    firebase_token_verifier: Callable[[str], dict[str, Any]] | None = None,
    firebase_user_deleter: Callable[[str], None] | None = None,
    agent_query_handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    agent_stream_query_handler: Callable[[dict[str, Any]], Iterator[dict[str, Any]]] | None = None,
    enable_public_query: bool | None = None,
    enable_internal_db: bool | None = None,
    enable_bridge_query: bool | None = None,
    ffmpeg_binary: str | None = None,
    auth_verifier: Callable[[str, str], Mapping[str, Any]] | None = None,
    allowed_callers: set[str] | frozenset[str] | None = None,
    auth_audience: str | None = None,
    require_auth: bool | None = None,
    max_upload_bytes: int | None = None,
    public_allowed_origins: tuple[str, ...] | None = None,
    public_app_base_url: str | None = None,
    metrics_registry: MetricsRegistry | None = None,
    gateway_config: GatewayConfig | None = None,
    audit_logger: AuditLogger | None = None,
) -> Flask:
    """Create the gateway app with overridable dependencies for tests."""

    configure_structured_logging()
    configure_tracing(
        environment=gateway_config.environment if gateway_config is not None else None,
        service_name="tailmate-db-gateway",
    )
    if metrics_registry is not None:
        set_metrics_registry(metrics_registry)
    app = Flask(__name__)
    resolved_gateway_config = gateway_config
    resolved_db_connection_factory = db_connection_factory
    resolved_user_privacy_service = user_privacy_service
    resolved_public_query_rate_limiter = public_query_rate_limiter
    resolved_knowledge_embedding_client = knowledge_embedding_client
    resolved_knowledge_engine_factory = None
    resolved_audio_transcriber = audio_transcriber

    def require_gateway_config() -> GatewayConfig:
        nonlocal resolved_gateway_config
        if resolved_gateway_config is None:
            resolved_gateway_config = GatewayConfig.from_env()
        return resolved_gateway_config

    def build_connection_backed_engine_factory(
        connection_factory: Callable[[], pg8000.dbapi.Connection],
    ):
        """Adapt a raw connection factory to the KB management engine contract."""

        class _ConnectionBackedEngine:
            def __init__(self, connection: pg8000.dbapi.Connection) -> None:
                self._connection = connection

            def raw_connection(self) -> pg8000.dbapi.Connection:
                return self._connection

            def dispose(self) -> None:
                return None

        class _ConnectionBackedEngineFactory:
            def create(self) -> _ConnectionBackedEngine:
                return _ConnectionBackedEngine(connection_factory())

        return _ConnectionBackedEngineFactory()

    def require_user_privacy_service() -> UserPrivacyGatewayService:
        nonlocal resolved_user_privacy_service
        if resolved_user_privacy_service is None:
            resolved_user_privacy_service = build_gateway_user_privacy_service(
                require_gateway_config(),
                blob_store=blob_store,
                firebase_user_deleter=firebase_user_deleter,
            )
        return resolved_user_privacy_service

    def require_public_query_rate_limiter() -> SlidingWindowRateLimiter:
        nonlocal resolved_public_query_rate_limiter
        if resolved_public_query_rate_limiter is None:
            if resolved_gateway_config is None:
                resolved_public_query_rate_limiter = InMemorySlidingWindowRateLimiter()
            else:
                resolved_public_query_rate_limiter = build_public_query_rate_limiter(
                    resolved_gateway_config
                )
        return resolved_public_query_rate_limiter

    def require_knowledge_embedding_client():
        nonlocal resolved_knowledge_embedding_client
        if resolved_knowledge_embedding_client is None:
            resolved_knowledge_embedding_client = build_knowledge_embedding_client(
                require_gateway_config()
            )
        return resolved_knowledge_embedding_client

    def require_audio_transcriber() -> AudioTranscriber:
        nonlocal resolved_audio_transcriber
        if resolved_audio_transcriber is None:
            resolved_audio_transcriber = build_gateway_audio_transcriber(require_gateway_config())
        return resolved_audio_transcriber

    def require_knowledge_engine_factory():
        nonlocal resolved_knowledge_engine_factory
        if resolved_knowledge_engine_factory is None:
            if resolved_db_connection_factory is not None:
                resolved_knowledge_engine_factory = build_connection_backed_engine_factory(
                    resolved_db_connection_factory
                )
            else:
                resolved_knowledge_engine_factory = build_gateway_engine_factory(
                    require_gateway_config()
                )
        return resolved_knowledge_engine_factory

    public_query_enabled = (
        resolve_gateway_flag("TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY", default=False)
        if enable_public_query is None
        else enable_public_query
    )
    internal_db_enabled = (
        resolve_gateway_flag("TAILMATE_GATEWAY_ENABLE_INTERNAL_DB", default=True)
        if enable_internal_db is None
        else enable_internal_db
    )
    bridge_query_enabled = (
        resolve_gateway_flag("TAILMATE_GATEWAY_ENABLE_BRIDGE_QUERY", default=False)
        if enable_bridge_query is None
        else enable_bridge_query
    )
    app.config["ENABLE_PUBLIC_QUERY"] = public_query_enabled
    app.config["ENABLE_INTERNAL_DB"] = internal_db_enabled
    app.config["ENABLE_BRIDGE_QUERY"] = bridge_query_enabled
    configured_public_allowed_origins = (
        gateway_config.public_allowed_origins
        if gateway_config is not None
        else os.getenv("TAILMATE_PUBLIC_ALLOWED_ORIGINS")
    )
    app.config["PUBLIC_ALLOWED_ORIGINS"] = (
        tuple(public_allowed_origins)
        if public_allowed_origins is not None
        else parse_allowed_origins(configured_public_allowed_origins)
    )
    configured_public_app_base_url = (
        public_app_base_url
        if isinstance(public_app_base_url, str) and public_app_base_url.strip()
        else (
            gateway_config.public_app_base_url
            if gateway_config is not None
            else os.getenv("TAILMATE_PUBLIC_APP_BASE_URL", "https://tailmate-app.vercel.app")
        )
    )
    app.config["PUBLIC_APP_BASE_URL"] = normalize_public_app_base_url(
        str(configured_public_app_base_url)
    )

    if internal_db_enabled:
        config = (
            require_gateway_config()
            if blob_store is None or db_connection_factory is None or dog_profile_db_adapter is None
            else None
        )
        app.config["BLOB_STORE"] = blob_store or build_gateway_blob_store(config)
        app.config["DB_CONNECTION_FACTORY"] = (
            db_connection_factory or (lambda: get_db_connection(config))
        )
        app.config["DOG_PROFILE_DB_ADAPTER"] = (
            dog_profile_db_adapter
            or build_gateway_dog_profile_db_adapter(
                config,
                audit_logger=audit_logger or build_gateway_audit_logger(config),
            )
        )
        app.config["FFMPEG_BINARY"] = (
            ffmpeg_binary
            or (config.ffmpeg_binary if config is not None else os.getenv("FFMPEG_BINARY", "ffmpeg"))
        )
        app.config["MAX_CONTENT_LENGTH"] = resolve_max_upload_bytes(
            max_upload_bytes,
            config=config,
        )
        app.config["AUTH_ENABLED"] = resolve_auth_required(require_auth, config=config)
        app.config["AUTH_AUDIENCE"] = (
            auth_audience
            or (config.gateway_auth_audience if config is not None else None)
            or os.getenv("TAILMATE_DB_GATEWAY_AUTH_AUDIENCE")
            or os.getenv("TAILMATE_DB_GATEWAY_AUDIENCE")
            or os.getenv("TAILMATE_DB_GATEWAY_URL")
            or None
        )
        app.config["TOKEN_VERIFIER"] = auth_verifier or verify_gateway_id_token
        app.config["ALLOWED_CALLERS"] = (
            frozenset(allowed_callers)
            if allowed_callers is not None
            else parse_identity_allowlist(
                config.gateway_allowed_callers
                if config is not None
                else os.getenv("TAILMATE_DB_GATEWAY_ALLOWED_CALLERS")
            )
        )
        if app.config["AUTH_ENABLED"] and not app.config["AUTH_AUDIENCE"]:
            raise ConfigurationError(
                "TAILMATE_DB_GATEWAY_AUTH_AUDIENCE is required when gateway auth is enabled."
            )
        if app.config["AUTH_ENABLED"] and not app.config["ALLOWED_CALLERS"]:
            raise ConfigurationError(
                "TAILMATE_DB_GATEWAY_ALLOWED_CALLERS is required when gateway auth is enabled."
            )

    if public_query_enabled or bridge_query_enabled:
        config = (
            require_gateway_config()
            if user_identity_resolver is None or agent_query_handler is None
            else None
        )
        app.config["USER_IDENTITY_RESOLVER"] = (
            user_identity_resolver or build_gateway_user_identity_resolver(config)
        )
        resolved_agent_query_handler = agent_query_handler or build_agent_query_handler(config)
        app.config["AGENT_QUERY_HANDLER"] = resolved_agent_query_handler
        app.config["AGENT_STREAM_QUERY_HANDLER"] = (
            agent_stream_query_handler
            or (
                build_agent_stream_query_handler(config)
                if config is not None
                else build_single_payload_stream_query_handler(resolved_agent_query_handler)
            )
        )

    if public_query_enabled:
        config = require_gateway_config() if firebase_token_verifier is None else None
        app.config["FIREBASE_TOKEN_VERIFIER"] = (
            firebase_token_verifier or build_firebase_token_verifier(config)
        )

    @app.errorhandler(TailmateError)
    def handle_tailmate_error(exc: TailmateError):
        current_app.logger.warning(
            "gateway_request_failed",
            extra={
                "status_code": exc.code,
                "error_type": exc.error_type,
                "error_message": str(exc),
            },
        )
        return jsonify({"error": str(exc)}), exc.code

    @app.errorhandler(RequestEntityTooLarge)
    def handle_request_too_large(exc: RequestEntityTooLarge):
        del exc
        max_bytes = int(current_app.config.get("MAX_CONTENT_LENGTH", DEFAULT_MAX_UPLOAD_BYTES))
        return jsonify({"error": f"Upload exceeds the configured {max_bytes}-byte limit."}), 413

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc: Exception):
        if isinstance(exc, HTTPException):
            return exc
        current_app.logger.exception("gateway_unexpected_error")
        return jsonify({"error": str(exc)}), 500

    @app.before_request
    def bind_request_logging_context():
        request_id = (
            request.headers.get(REQUEST_ID_HEADER)
            or request.headers.get("X-Request-Id")
            or ""
        ).strip() or generate_request_id()
        trace_id = (request.headers.get(TRACE_ID_HEADER) or "").strip() or generate_trace_id()
        g.request_id = request_id
        g.trace_id = trace_id
        g.user_id = None
        g.request_started_at = time.perf_counter()
        g.request_log_token = set_log_context(
            LogContext(request_id=request_id, trace_id=trace_id)
        )
        g.trace_context_token = attach_trace_context(request.headers)
        view_args = request.view_args or {}
        user_id = view_args.get("user_id")
        session_id = view_args.get("session_id")
        if isinstance(user_id, str) and user_id.strip():
            update_log_context(user_id=user_id)
        if isinstance(session_id, str) and session_id.strip():
            update_log_context(session_id=session_id)
        return None

    @app.after_request
    def attach_request_logging_context(response):
        request_id = getattr(g, "request_id", None)
        if isinstance(request_id, str) and request_id.strip():
            response.headers[REQUEST_ID_HEADER] = request_id
        trace_id = getattr(g, "trace_id", None)
        if isinstance(trace_id, str) and trace_id.strip():
            response.headers[TRACE_ID_HEADER] = trace_id
        started_at = getattr(g, "request_started_at", None)
        latency_ms = (
            round((time.perf_counter() - started_at) * 1000, 2)
            if isinstance(started_at, float)
            else None
        )
        current_app.logger.info(
            "gateway_request_completed",
            extra={
                "request_method": request.method,
                "request_path": request.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )
        if is_public_browser_path(request.path):
            apply_public_cors_headers(
                response,
                allowed_origins=current_app.config["PUBLIC_ALLOWED_ORIGINS"],
                request_origin=request.headers.get("Origin"),
            )
        return response

    @app.teardown_request
    def clear_request_logging_context(exc: Exception | None):
        del exc
        trace_token = getattr(g, "trace_context_token", None)
        if trace_token is not None:
            detach_trace_context(trace_token)
        token = getattr(g, "request_log_token", None)
        if token is not None:
            reset_log_context(token)

    @app.before_request
    def authenticate_internal_gateway_request():
        if not current_app.config.get("ENABLE_INTERNAL_DB"):
            return None
        if request.endpoint not in INTERNAL_DB_ENDPOINTS:
            return None
        if not current_app.config["AUTH_ENABLED"]:
            return None
        if request.headers.get("X-Serverless-Authorization") and not request.headers.get(
            "Authorization"
        ):
            raise AuthenticationError(
                "Gateway app-layer verification requires the Authorization header, not only X-Serverless-Authorization."
            )

        token = extract_bearer_token(request.headers.get("Authorization"))
        expected_audience = str(current_app.config["AUTH_AUDIENCE"])
        try:
            claims = current_app.config["TOKEN_VERIFIER"](token, expected_audience)
        except TailmateError:
            raise
        except Exception as exc:
            raise AuthenticationError("Invalid or expired Authorization bearer token.") from exc

        caller = build_authenticated_caller(claims)
        g.gateway_caller = caller

        if request.method in WRITE_METHODS:
            allowed_identities = current_app.config["ALLOWED_CALLERS"]
            if caller.identity not in allowed_identities and caller.subject not in allowed_identities:
                raise AuthorizationError(
                    f"Caller '{caller.identity}' is not allowed to perform write operations."
                )
        return None

    @app.route("/health", methods=["GET"])
    def health():
        checks: dict[str, str] = {}
        errors: dict[str, str] = {}
        status_code = 200

        if internal_db_enabled:
            try:
                check_database_health(current_app.config["DB_CONNECTION_FACTORY"])
                checks["db"] = "ok"
            except Exception as exc:
                current_app.logger.exception("Gateway database health check failed: %s", exc)
                checks["db"] = "error"
                errors["db"] = str(exc)
                status_code = 503
        else:
            checks["db"] = "skipped"

        payload = {
            "status": "ok" if status_code == 200 else "error",
            "checks": checks,
            "public_query_enabled": public_query_enabled,
            "internal_db_enabled": internal_db_enabled,
            "bridge_query_enabled": bridge_query_enabled,
        }
        if errors:
            payload["errors"] = errors
        return jsonify(payload), status_code

    def require_trusted_user_id() -> str:
        trusted_user_id = (request.headers.get(TRUSTED_USER_ID_HEADER) or "").strip()
        if not trusted_user_id:
            raise AuthenticationError(f"{TRUSTED_USER_ID_HEADER} header is required.")
        g.user_id = trusted_user_id
        update_log_context(user_id=trusted_user_id)
        return trusted_user_id

    def require_active_firebase_user(view):
        @wraps(view)
        def _wrapped(*args: Any, **kwargs: Any):
            claims = require_firebase_claims()
            firebase_uid = extract_firebase_uid(claims)
            identity = current_app.config["USER_IDENTITY_RESOLVER"].resolve_platform_identity(
                platform=PUBLIC_QUERY_PLATFORM,
                platform_user_id=firebase_uid,
            )
            if identity is None:
                raise AuthorizationError("The authenticated user is not bound to a Tailmate account.")
            if identity.status != "active":
                raise AuthorizationError("The authenticated user account is not active.")
            if identity.connection_status != "active":
                raise AuthorizationError("The authenticated platform connection is not active.")
            g.authenticated_user = identity
            g.user_id = identity.user_id
            update_log_context(user_id=identity.user_id)
            return view(*args, **kwargs)

        return _wrapped

    def require_matching_firebase_user(view):
        @wraps(view)
        def _wrapped(user_id: str, *args: Any, **kwargs: Any):
            claims = require_firebase_claims()
            firebase_uid = extract_firebase_uid(claims)
            normalized_user_id = user_id.strip()
            assert_owner(
                normalized_user_id,
                firebase_uid,
                resource_label="the requested user account",
            )
            account = current_app.config["USER_IDENTITY_RESOLVER"].load_user(normalized_user_id)
            if account is None:
                raise NotFoundError("The requested user does not exist.")
            g.authenticated_account = account
            g.user_id = normalized_user_id
            update_log_context(user_id=normalized_user_id)
            return view(normalized_user_id, *args, **kwargs)

        return _wrapped

    if public_query_enabled:
        @app.route(PUBLIC_USER_REGISTER_PATH, methods=["POST"])
        def register_user():
            claims = require_firebase_claims()
            firebase_uid = extract_firebase_uid(claims)
            existing_identity = current_app.config["USER_IDENTITY_RESOLVER"].resolve_platform_identity(
                platform=PUBLIC_QUERY_PLATFORM,
                platform_user_id=firebase_uid,
            )
            identity = current_app.config["USER_IDENTITY_RESOLVER"].register_web_user(
                firebase_uid=firebase_uid,
            )
            status_code = 200 if existing_identity is not None else 201
            account = current_app.config["USER_IDENTITY_RESOLVER"].load_user(identity.user_id)
            if account is None:
                raise AuthorizationError("The authenticated user is not bound to a Tailmate account.")
            return jsonify(
                {
                    "user": serialize_user_account(account),
                    "connection": serialize_platform_identity(identity),
                }
            ), status_code

        @app.route(PUBLIC_USER_ACTIVATE_PATH, methods=["POST"])
        def activate_user():
            claims = require_firebase_claims()
            firebase_uid = extract_firebase_uid(claims)
            account = current_app.config["USER_IDENTITY_RESOLVER"].activate_user(
                user_id=firebase_uid,
            )
            return jsonify({"user": serialize_user_account(account)})

        @app.route(PUBLIC_USER_EXPORT_PATH, methods=["GET"])
        @require_matching_firebase_user
        def export_user_data(user_id: str):
            return jsonify(require_user_privacy_service().export_user_data(user_id=user_id))

        @app.route(PUBLIC_USER_DELETE_PATH, methods=["DELETE"])
        @require_matching_firebase_user
        def delete_user_data(user_id: str):
            return jsonify(require_user_privacy_service().delete_user_data(user_id=user_id))

        @app.route(PUBLIC_USER_CONNECTIONS_PATH, methods=["POST"])
        @require_active_firebase_user
        def create_or_update_platform_connection(platform: str):
            try:
                normalized_platform = normalize_connection_platform(platform)
                if normalized_platform == PUBLIC_QUERY_PLATFORM:
                    raise ConflictError("The web platform connection is managed through registration.")
                authenticated_user: ResolvedPlatformIdentity = g.authenticated_user
                raw_payload = request.get_json(silent=True) or {}
                connection_payload: PlatformConnectionInput = normalize_platform_connection_input(
                    raw_payload
                )
                connection_status = normalize_connection_status(
                    connection_payload.get("status", "pending_verification")
                )
                identity = current_app.config["USER_IDENTITY_RESOLVER"].upsert_platform_connection(
                    user_id=authenticated_user.user_id,
                    platform=normalized_platform,
                    platform_user_id=connection_payload["platform_user_id"],
                    status=connection_status,
                )
                return jsonify({"connection": serialize_platform_identity(identity)})
            except (TypeError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400

        @app.route(PUBLIC_USER_CONNECTIONS_PATH, methods=["DELETE"])
        @require_active_firebase_user
        def disconnect_platform_connection(platform: str):
            try:
                normalized_platform = normalize_connection_platform(platform)
                if normalized_platform == PUBLIC_QUERY_PLATFORM:
                    raise ConflictError("The web platform connection cannot be disconnected.")
                authenticated_user: ResolvedPlatformIdentity = g.authenticated_user
                identity = current_app.config[
                    "USER_IDENTITY_RESOLVER"
                ].disconnect_platform_connection(
                    user_id=authenticated_user.user_id,
                    platform=normalized_platform,
                )
                if identity is None:
                    raise NotFoundError("The requested platform connection does not exist.")
                return jsonify({"connection": serialize_platform_identity(identity)})
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

        @app.route(PUBLIC_AGENT_QUERY_PATH, methods=["POST"])
        @require_active_firebase_user
        def public_agent_query():
            try:
                with start_span(
                    "db_gateway.public_agent_query",
                    attributes={
                        "http.method": request.method,
                        "http.route": PUBLIC_AGENT_QUERY_PATH,
                    },
                ):
                    wants_stream = "text/event-stream" in (
                        request.headers.get("Accept", "").lower()
                    ) or request.args.get("stream") == "1"
                    normalized_request = normalize_public_agent_query_input(
                        request.get_json(silent=True) or {}
                    )
                    authenticated_user: ResolvedPlatformIdentity = g.authenticated_user
                    rate_limit_decision = require_public_query_rate_limiter().check(
                        user_id=authenticated_user.user_id,
                    )
                    if not rate_limit_decision.allowed:
                        retry_after_seconds = rate_limit_decision.retry_after_seconds or 1
                        current_app.logger.warning(
                            "public_query_rate_limit_exceeded",
                            extra={
                                "user_id": authenticated_user.user_id,
                                "limit": rate_limit_decision.limit,
                                "window_seconds": rate_limit_decision.window_seconds,
                                "retry_after_seconds": retry_after_seconds,
                            },
                        )
                        response = jsonify(
                            {
                                "error": (
                                    "Rate limit exceeded for the public query route. "
                                    "Please retry later."
                                )
                            }
                        )
                        response.headers["Retry-After"] = str(retry_after_seconds)
                        response.headers["X-RateLimit-Limit"] = str(rate_limit_decision.limit)
                        response.headers["X-RateLimit-Remaining"] = "0"
                        response.headers["X-RateLimit-Window-Seconds"] = str(
                            rate_limit_decision.window_seconds
                        )
                        return response, 429
                    external_session_id = normalized_request.get(
                        "session_id",
                        generate_external_session_id(),
                    )
                    internal_session_id = build_internal_session_id(
                        user_id=authenticated_user.user_id,
                        platform=authenticated_user.platform or PUBLIC_QUERY_PLATFORM,
                        external_conversation_id=external_session_id,
                    )
                    update_log_context(
                        user_id=authenticated_user.user_id,
                        session_id=internal_session_id,
                    )
                    metadata: dict[str, Any] = {
                        "user_id": authenticated_user.user_id,
                        "request_id": g.request_id,
                        "trace_id": g.trace_id,
                        "channel": authenticated_user.platform or PUBLIC_QUERY_PLATFORM,
                    }
                    inject_trace_context(metadata)
                    if "dog_id" in normalized_request:
                        metadata["dog_id"] = normalized_request["dog_id"]
                    strip_request = normalized_request.get(STRIP_METADATA_REQUEST_METADATA_KEY)
                    if strip_request is not None:
                        metadata[STRIP_METADATA_REQUEST_METADATA_KEY] = {
                            **dict(strip_request),
                            "session_id": internal_session_id,
                        }
                    payload = {
                        "session_id": internal_session_id,
                        "message": normalized_request["message"],
                        "metadata": metadata,
                    }
                    if wants_stream:
                        stream_handler = current_app.config["AGENT_STREAM_QUERY_HANDLER"]

                        def _stream_response() -> Iterator[str]:
                            try:
                                for event in stream_handler(payload):
                                    if not isinstance(event, dict):
                                        raise RuntimeError(
                                            "The Agent Engine streaming response was not JSON-serializable."
                                        )
                                    proxied_event = dict(event)
                                    proxied_event["session_id"] = external_session_id
                                    output = proxied_event.get("output")
                                    if isinstance(output, dict):
                                        proxied_output = dict(output)
                                        proxied_output["session_id"] = external_session_id
                                        proxied_event["output"] = proxied_output
                                    yield format_sse_event(proxied_event)
                            except TailmateError as exc:
                                yield format_sse_event(
                                    {
                                        "event": "query.completed",
                                        "session_id": external_session_id,
                                        "output": {
                                            "session_id": external_session_id,
                                            "response": "",
                                            "metadata": {
                                                "dog_id": normalized_request.get("dog_id")
                                            },
                                            "error": exc.to_error_detail(),
                                        },
                                    }
                                )
                            except Exception:
                                error = InternalError()
                                yield format_sse_event(
                                    {
                                        "event": "query.completed",
                                        "session_id": external_session_id,
                                        "output": {
                                            "session_id": external_session_id,
                                            "response": "",
                                            "metadata": {
                                                "dog_id": normalized_request.get("dog_id")
                                            },
                                            "error": error.to_error_detail(),
                                        },
                                    }
                                )

                        response = Response(
                            stream_with_context(_stream_response()),
                            mimetype="text/event-stream",
                        )
                        response.headers["Cache-Control"] = "no-cache"
                        response.headers["X-Accel-Buffering"] = "no"
                        return response

                    response_payload = current_app.config["AGENT_QUERY_HANDLER"](payload)
                    proxied_payload = dict(response_payload)
                    proxied_payload["session_id"] = external_session_id
                    return jsonify(proxied_payload)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400

    if internal_db_enabled:

        if bridge_query_enabled:

            @app.route("/bridge/users/ensure", methods=["POST"])
            def ensure_bridge_platform_user():
                try:
                    normalized_request: BridgePlatformUserInput = (
                        normalize_bridge_platform_user_input(request.get_json(silent=True) or {})
                    )
                    normalized_platform = normalize_connection_platform(
                        normalized_request["platform"]
                    )
                    if normalized_platform == PUBLIC_QUERY_PLATFORM:
                        raise ValueError("platform 'web' is not supported for bridge users.")

                    identity, created = current_app.config[
                        "USER_IDENTITY_RESOLVER"
                    ].ensure_active_platform_user(
                        platform=normalized_platform,
                        platform_user_id=normalized_request["platform_user_id"],
                    )
                    update_log_context(user_id=identity.user_id)
                    account = current_app.config["USER_IDENTITY_RESOLVER"].load_user(identity.user_id)
                    if account is None:
                        raise DomainError("The platform user could not be provisioned.")
                    return (
                        jsonify(
                            {
                                "created": created,
                                "user": serialize_user_account(account),
                                "connection": serialize_platform_identity(identity),
                            }
                        ),
                        201 if created else 200,
                    )
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400

            @app.route("/bridge/webhooks/claim", methods=["POST"])
            def claim_bridge_webhook_event():
                try:
                    raw_payload = request.get_json(silent=True) or {}
                    message_id = str(raw_payload.get("message_id", "")).strip()
                    claimed = claim_processed_webhook_event(
                        current_app.config["DB_CONNECTION_FACTORY"],
                        message_id=message_id,
                    )
                    return jsonify({"claimed": claimed}), 201 if claimed else 200
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400

            @app.route("/bridge/webhooks/release", methods=["POST"])
            def release_bridge_webhook_event():
                try:
                    raw_payload = request.get_json(silent=True) or {}
                    message_id = str(raw_payload.get("message_id", "")).strip()
                    released = release_processed_webhook_event(
                        current_app.config["DB_CONNECTION_FACTORY"],
                        message_id=message_id,
                    )
                    return jsonify({"released": released}), 200
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400

            @app.route("/bridge/query", methods=["POST"])
            def bridge_query():
                try:
                    with start_span(
                        "db_gateway.bridge_query",
                        attributes={
                            "http.method": request.method,
                            "http.route": "/bridge/query",
                        },
                    ):
                        normalized_request: BridgeQueryInput = normalize_bridge_query_input(
                            request.get_json(silent=True) or {}
                        )
                        normalized_platform = normalize_connection_platform(
                            normalized_request["platform"]
                        )
                        if normalized_platform == PUBLIC_QUERY_PLATFORM:
                            raise ValueError("platform 'web' is not supported for bridge queries.")

                        identity = current_app.config[
                            "USER_IDENTITY_RESOLVER"
                        ].resolve_platform_identity(
                            platform=normalized_platform,
                            platform_user_id=normalized_request["platform_user_id"],
                        )
                        external_session_id = normalized_request.get(
                            "session_id",
                            generate_external_session_id(),
                        )
                        if identity is None:
                            raise AuthorizationError(
                                "The authenticated platform user is not bound to a Tailmate account."
                            )
                        if identity.status != "active":
                            raise AuthorizationError("The authenticated user account is not active.")
                        if identity.connection_status != "active":
                            raise AuthorizationError(
                                "The authenticated platform connection is not active."
                            )
                        internal_session_id = build_internal_session_id(
                            user_id=identity.user_id,
                            platform=identity.platform,
                            external_conversation_id=external_session_id,
                        )
                        update_log_context(user_id=identity.user_id, session_id=internal_session_id)
                        metadata: dict[str, Any] = {
                            "user_id": identity.user_id,
                            "request_id": g.request_id,
                            "trace_id": g.trace_id,
                            "channel": normalized_platform,
                        }
                        inject_trace_context(metadata)
                        if "dog_id" in normalized_request:
                            metadata["dog_id"] = normalized_request["dog_id"]
                        try:
                            response_payload = current_app.config["AGENT_QUERY_HANDLER"](
                                {
                                    "session_id": internal_session_id,
                                    "message": normalized_request["message"],
                                    "metadata": metadata,
                                }
                            )
                        except Exception:
                            current_app.logger.exception(
                                "bridge_query_agent_handler_error"
                            )
                            response_payload = {
                                "session_id": internal_session_id,
                                "response": "",
                                "metadata": {},
                                "error": {
                                    "type": "InternalError",
                                    "message": "An unexpected error occurred.",
                                },
                            }
                        proxied_payload = dict(response_payload)
                        proxied_payload["session_id"] = external_session_id
                        return jsonify(proxied_payload)
                except ValueError as exc:
                    return jsonify({"error": str(exc)}), 400

        @app.route("/metrics", methods=["GET"])
        def metrics():
            return current_app.response_class(
                render_prometheus_metrics(),
                content_type="text/plain; version=0.0.4; charset=utf-8",
            )

        @app.route("/sessions/<session_id>", methods=["GET"])
        def load_session(session_id: str):
            with closing(app.config["DB_CONNECTION_FACTORY"]()) as conn, closing(
                conn.cursor()
            ) as cursor:
                cursor.execute(
                    """
                    SELECT session_id, turns, attributes
                    FROM conversation_sessions
                    WHERE session_id = %s
                    """,
                    [session_id],
                )
                row = cursor.fetchone()

            if row is None:
                return jsonify(
                    {
                        "session_id": session_id,
                        "turns": [],
                        "attributes": {},
                    }
                )

            return jsonify(
                {
                    "session_id": row[0],
                    "turns": normalize_json_value(row[1], default=[]),
                    "attributes": normalize_json_value(row[2], default={}),
                }
            )

        @app.route("/sessions/<session_id>", methods=["PUT"])
        def save_session(session_id: str):
            data = request.get_json(silent=True) or {}
            turns = data.get("turns", [])
            attributes = data.get("attributes", {})
            if not isinstance(turns, list):
                return jsonify({"error": "`turns` must be a list."}), 400
            if not isinstance(attributes, dict):
                return jsonify({"error": "`attributes` must be an object."}), 400

            existing_attributes = load_session_attributes(
                app.config["DB_CONNECTION_FACTORY"],
                session_id,
            )
            normalized_attributes = merge_session_attributes(existing_attributes, attributes)
            with closing(app.config["DB_CONNECTION_FACTORY"]()) as conn, closing(
                conn.cursor()
            ) as cursor:
                cursor.execute(
                    """
                    INSERT INTO conversation_sessions (session_id, turns, attributes)
                    VALUES (%s, %s::jsonb, %s::jsonb)
                    ON CONFLICT (session_id)
                    DO UPDATE SET
                        turns = EXCLUDED.turns,
                        attributes = EXCLUDED.attributes
                    """,
                    [session_id, json.dumps(turns), json.dumps(normalized_attributes)],
                )
                conn.commit()

            return jsonify({"session_id": session_id, "saved": True})

        @app.route("/knowledge/search", methods=["POST"])
        def search_knowledge():
            try:
                normalized_request = normalize_knowledge_search_request(
                    request.get_json(silent=True) or {}
                )
                hits = search_knowledge_chunk_records(
                    require_knowledge_engine_factory(),
                    embedding=normalized_request.embedding,
                    locale=normalized_request.locale,
                    top_k=normalized_request.top_k,
                )
                return jsonify({"hits": [hit.model_dump(mode="json") for hit in hits]})
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            except TypeError as exc:
                return jsonify({"error": str(exc)}), 400
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        @app.route(INTERNAL_KB_CHUNKS_PATH, methods=["POST"])
        def create_knowledge_chunk():
            try:
                normalized_request = normalize_knowledge_chunk_input(
                    request.get_json(silent=True) or {}
                )
                result = create_knowledge_chunk_record(
                    require_knowledge_engine_factory(),
                    payload=normalized_request,
                    embedding_client=require_knowledge_embedding_client(),
                )
                return jsonify(result), 201
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            except TypeError as exc:
                return jsonify({"error": str(exc)}), 400

        @app.route(INTERNAL_KB_CHUNK_IMPORT_PATH, methods=["POST"])
        def import_knowledge_chunks():
            try:
                raw_payload = request.get_json(silent=True)
                if raw_payload is not None:
                    normalized_batch = normalize_knowledge_chunk_batch_input(raw_payload)
                else:
                    file_storage = request.files.get("file")
                    if file_storage is None or not file_storage.filename:
                        raise ValueError("A CSV or JSON file upload is required.")
                    records = load_knowledge_chunk_upload_records(
                        file_storage.read(),
                        content_type=file_storage.content_type,
                        filename=file_storage.filename,
                    )
                    normalized_batch = normalize_knowledge_chunk_batch_input(
                        {"chunks": [record.model_dump() for record in records]}
                    )
                result = import_knowledge_chunk_records(
                    require_knowledge_engine_factory(),
                    records=normalized_batch.chunks,
                    embedding_client=require_knowledge_embedding_client(),
                )
                return jsonify(result), 201
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            except TypeError as exc:
                return jsonify({"error": str(exc)}), 400

        @app.route(INTERNAL_KB_CHUNK_PATH, methods=["DELETE"])
        def delete_knowledge_chunk(chunk_id: str):
            result = delete_knowledge_chunk_record(
                require_knowledge_engine_factory(),
                chunk_id=chunk_id,
            )
            return jsonify(result)

        @app.route(INTERNAL_KB_CHUNKS_PATH, methods=["GET"])
        def preview_knowledge_chunks():
            try:
                normalized_request = normalize_knowledge_chunk_preview_input(
                    {
                        "query": request.args.get("query", ""),
                        "locale": request.args.get("locale") or "en-AU",
                        "top_k": request.args.get("top_k") or 3,
                    }
                )
                hits = preview_knowledge_chunk_records(
                    require_knowledge_engine_factory(),
                    payload=normalized_request,
                    embedding_client=require_knowledge_embedding_client(),
                )
                return jsonify(
                    {
                        "query": normalized_request.query,
                        "locale": normalized_request.locale,
                        "top_k": normalized_request.top_k,
                        "hits": [hit.model_dump(mode="json") for hit in hits],
                    }
                )
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            except TypeError as exc:
                return jsonify({"error": str(exc)}), 400

        @app.route("/dog-profiles", methods=["POST"])
        def create_dog_profile():
            trusted_user_id = require_trusted_user_id()
            normalized_request = normalize_create_dog_profile_input(
                request.get_json(silent=True) or {}
            )
            assert_owner(
                normalized_request.user_id,
                trusted_user_id,
                resource_label="the dog profile owner",
            )

            existing_attributes = load_session_attributes(
                current_app.config["DB_CONNECTION_FACTORY"],
                normalized_request.session_id,
            )
            existing_bound_dog_id = normalize_bound_dog_id(
                normalize_session_attributes(existing_attributes)
            )
            if existing_bound_dog_id:
                raise AuthorizationError(
                    f"Session '{normalized_request.session_id}' is already bound to a dog profile."
                )

            result = current_app.config["DOG_PROFILE_DB_ADAPTER"].create_profile(normalized_request)
            try:
                bind_session_to_dog(
                    current_app.config["DB_CONNECTION_FACTORY"],
                    session_id=normalized_request.session_id,
                    dog_id=result.dog_id,
                )
            except Exception:
                cleanup_created_dog_profile(
                    current_app.config["DOG_PROFILE_DB_ADAPTER"],
                    dog_id=result.dog_id,
                )
                raise
            return jsonify(result.model_dump(mode="json")), 201

        @app.route("/dog-profiles", methods=["GET"])
        def list_dog_profiles():
            trusted_user_id = require_trusted_user_id()
            profiles = current_app.config["DOG_PROFILE_DB_ADAPTER"].list_profiles(
                requesting_user_id=trusted_user_id,
            )
            return jsonify(
                {
                    "profiles": [
                        profile.model_dump(mode="json")
                        for profile in profiles
                    ]
                }
            )

        @app.route("/dog-profiles/<dog_id>", methods=["GET"])
        def load_dog_profile(dog_id: str):
            trusted_user_id = require_trusted_user_id()
            session_id = (request.args.get("session_id") or "").strip()
            if session_id:
                require_session_bound_dog(
                    current_app.config["DB_CONNECTION_FACTORY"],
                    session_id=session_id,
                    dog_id=dog_id,
                )
            profile = current_app.config["DOG_PROFILE_DB_ADAPTER"].load_profile(
                dog_id,
                requesting_user_id=trusted_user_id,
            )
            if profile is None:
                return jsonify({"found": False, "dog_id": dog_id})
            return jsonify({"found": True, "profile": profile.model_dump(mode="json")})

        @app.route("/dog-profiles/<dog_id>/enrich", methods=["POST"])
        def enrich_dog_profile(dog_id: str):
            payload = request.get_json(silent=True) or {}
            trusted_user_id = require_trusted_user_id()
            session_id = str(payload.get("session_id") or "").strip()
            if session_id:
                require_session_bound_dog(
                    current_app.config["DB_CONNECTION_FACTORY"],
                    session_id=session_id,
                    dog_id=dog_id,
                )
            normalized_request = normalize_enrich_dog_profile_input(
                {
                    "dog_id": dog_id,
                    "requesting_user_id": trusted_user_id,
                    "user_message": payload.get("user_message", ""),
                    "current_profile": payload.get("current_profile"),
                }
            )
            extraction_result = normalize_extraction_result(payload.get("extraction_result") or {})
            result = current_app.config["DOG_PROFILE_DB_ADAPTER"].enrich_profile(
                normalized_request,
                extraction_result,
            )
            return jsonify(result.model_dump(mode="json"))

        @app.route("/media/upload", methods=["POST"])
        @app.route("/media/strip-metadata", methods=["POST"])
        def upload_media():
            file_storage = request.files.get("file")
            if file_storage is None or not file_storage.filename:
                return jsonify({"error": "`file` is required."}), 400

            trusted_user_id = require_trusted_user_id()
            dog_id = request.form.get("dog_id", "").strip()
            session_id = (request.form.get("session_id") or "").strip()
            raw_bytes = file_storage.read()
            content_type = file_storage.content_type or request.form.get("content_type", "")
            upload_limit = resolve_media_upload_limit(
                content_type,
                max_upload_bytes=int(current_app.config.get("MAX_CONTENT_LENGTH", DEFAULT_MAX_UPLOAD_BYTES)),
            )
            if len(raw_bytes) > upload_limit:
                raise RequestEntityTooLarge()
            if session_id:
                require_session_bound_dog(
                    current_app.config["DB_CONNECTION_FACTORY"],
                    session_id=session_id,
                    dog_id=dog_id,
                )

            owned_profile = current_app.config["DOG_PROFILE_DB_ADAPTER"].load_profile(
                dog_id,
                requesting_user_id=trusted_user_id,
            )
            if owned_profile is None:
                raise AuthorizationError(
                    f"Dog profile '{dog_id}' is not owned by the requesting user."
                )

            raw_request = {
                "dog_id": dog_id,
                "resource_kind": request.form.get("resource_kind", ""),
                "filename": file_storage.filename,
                "content_type": content_type,
                "payload_base64": base64.b64encode(raw_bytes).decode("ascii"),
            }
            if session_id:
                raw_request["session_id"] = session_id
            try:
                normalized_request = normalize_strip_metadata_request(raw_request)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            direct_store = DirectSanitizedMediaStore(
                blob_store=current_app.config["BLOB_STORE"],
                audio_transcriber=(
                    require_audio_transcriber() if content_type.startswith("audio/") else None
                ),
                ffmpeg_binary=current_app.config["FFMPEG_BINARY"],
            )
            result = direct_store.strip_and_store(normalized_request)
            try:
                caller = get_authenticated_caller()
                persist_media_asset(
                    current_app.config["DB_CONNECTION_FACTORY"],
                    result,
                    uploaded_by=None if caller is None else caller.identity,
                )
            except MediaAssetPersistenceError:
                try:
                    current_app.config["BLOB_STORE"].delete(result["logical_path"])
                except Exception as cleanup_error:
                    current_app.logger.warning(
                        "Failed to delete sanitized media after gateway persistence failure.",
                        exc_info=cleanup_error,
                    )
                raise
            return jsonify(result), 201

    return app
