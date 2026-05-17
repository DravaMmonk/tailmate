from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
import json

from PIL import Image
from werkzeug.utils import secure_filename

from tailmate.adapters.db_gateway import gateway_app
from tailmate.adapters.db_gateway.identity import ResolvedPlatformIdentity, ResolvedUserAccount
from tailmate.adapters.db_gateway.gateway_app import create_app
from tailmate.adapters.db_gateway.rate_limiter import InMemorySlidingWindowRateLimiter
from tailmate.contracts.constants import (
    PUBLIC_AGENT_QUERY_PATH,
    REQUEST_ID_HEADER,
    TRACE_ID_HEADER,
    PUBLIC_USER_ACTIVATE_PATH,
    PUBLIC_USER_CONNECTIONS_PATH,
    PUBLIC_USER_DELETE_PATH,
    PUBLIC_USER_EXPORT_PATH,
    PUBLIC_USER_REGISTER_PATH,
    STRIP_METADATA_REQUEST_METADATA_KEY,
    TRUSTED_USER_ID_HEADER,
)
from tailmate.contracts.dog_profile import (
    CreateDogProfileOutput,
    DogProfile,
    EnrichDogProfileOutput,
)
from tailmate.contracts.errors import AuthorizationError
from tailmate.contracts.knowledge import KnowledgeSearchHit
from tailmate.contracts.types import MAX_QUERY_MESSAGE_LENGTH
from tailmate.contracts import types as contract_types
from tailmate.metrics import MetricsRegistry, record_session_started, reset_metrics_registry


WRITER_EMAIL = "tailmate-agent@test.iam.gserviceaccount.com"
TELEGRAM_CONNECTION_PATH = PUBLIC_USER_CONNECTIONS_PATH.replace("<platform>", "telegram")
USER_DELETE_PATH = PUBLIC_USER_DELETE_PATH.replace("<user_id>", "user-1")
USER_EXPORT_PATH = PUBLIC_USER_EXPORT_PATH.replace("<user_id>", "user-1")


def fake_auth_verifier(token: str, audience: str) -> dict[str, str]:
    del audience
    if token == "writer-token":
        return {"sub": "writer-sub", "email": WRITER_EMAIL}
    if token == "reader-token":
        return {"sub": "reader-sub", "email": "analytics@test.iam.gserviceaccount.com"}
    raise ValueError("invalid token")


def build_auth_headers(
    token: str = "writer-token",
    *,
    user_id: str | None = "user-1",
) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if user_id is not None:
        headers[TRUSTED_USER_ID_HEADER] = user_id
    return headers


class FakeBlobStore:
    def __init__(self) -> None:
        self.payloads: dict[str, tuple[str, bytes]] = {}
        self.deleted: list[str] = []

    def put(self, logical_path: str, content_type: str, payload: bytes) -> str:
        self.payloads[logical_path] = (content_type, payload)
        return logical_path

    def resolve_resource(self, logical_path: str) -> str:
        return f"gs://tailmate-media/{logical_path}"

    def delete(self, logical_path: str) -> None:
        self.deleted.append(logical_path)
        self.payloads.pop(logical_path, None)


class FakeCursor:
    def __init__(
        self,
        *,
        session_rows: dict[str, dict[str, object]] | None = None,
        fetchone_result=None,
        fetchall_result: list[tuple[object, ...]] | None = None,
        processed_webhook_event_ids: set[str] | None = None,
    ) -> None:
        self.session_rows = session_rows or {}
        self.processed_webhook_event_ids = processed_webhook_event_ids or set()
        self.statements: list[tuple[str, list[object] | None]] = []
        self._last_statement = ""
        self._last_params: list[object] | None = None
        self._fetchone_result = fetchone_result
        self._fetchall_result = fetchall_result or []

    def execute(self, statement: str, params=None) -> None:
        normalized_params = list(params) if params is not None else None
        self.statements.append((statement, normalized_params))
        self._last_statement = statement
        self._last_params = normalized_params
        if normalized_params is None:
            return
        if "INSERT INTO processed_webhook_events" in statement:
            message_id = str(normalized_params[0])
            if message_id in self.processed_webhook_event_ids:
                self._fetchone_result = None
            else:
                self.processed_webhook_event_ids.add(message_id)
                self._fetchone_result = (message_id,)
            return
        if "DELETE FROM processed_webhook_events" in statement:
            message_id = str(normalized_params[0])
            if message_id in self.processed_webhook_event_ids:
                self.processed_webhook_event_ids.remove(message_id)
                self._fetchone_result = (message_id,)
            else:
                self._fetchone_result = None
            return
        if "INSERT INTO conversation_sessions" in statement:
            self.session_rows[str(normalized_params[0])] = json.loads(str(normalized_params[2]))
            return
        if "UPDATE conversation_sessions" in statement and "SET attributes" in statement:
            self.session_rows[str(normalized_params[1])] = json.loads(str(normalized_params[0]))

    def fetchone(self):
        if self._last_params is None:
            if self._last_statement.strip() == "SELECT 1":
                return (1,)
            return self._fetchone_result
        if "SELECT session_id, turns, attributes" in self._last_statement:
            session_id = str(self._last_params[0])
            session_row = self.session_rows.get(session_id)
            if session_row is None:
                return self._fetchone_result
            return (session_id, [], session_row)
        if "SELECT attributes" in self._last_statement:
            session_row = self.session_rows.get(str(self._last_params[0]))
            if session_row is None:
                return self._fetchone_result
            return (session_row,)
        return self._fetchone_result

    def fetchall(self):
        return list(self._fetchall_result)

    def close(self) -> None:
        return None


class FailingCursor(FakeCursor):
    def execute(self, statement: str, params=None) -> None:
        if statement.strip() == "SELECT 1":
            raise RuntimeError("database unavailable")
        super().execute(statement, params)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        return None


class FakeHttpResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object | None = None,
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.reason = text or "error"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise gateway_app.requests.HTTPError(response=self)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeHttpSession:
    def __init__(self, response: FakeHttpResponse) -> None:
        self.response = response
        self.requests: list[dict[str, object]] = []

    def request(self, method: str, url: str, **kwargs):
        self.requests.append({"method": method, "url": url, **kwargs})
        return self.response


class FakeDogProfileDBAdapter:
    def __init__(self) -> None:
        self.created_name: str | None = None
        self.created_user_id: str | None = None
        self.deleted_dog_ids: list[str] = []
        self.last_load_request: tuple[str, str] | None = None
        self.last_enrich_request = None
        self.last_extraction_result = None
        self.profiles = {
            "dog-1": DogProfile(dog_id="dog-1", user_id="user-1", name="DouDou"),
            "dog-2": DogProfile(dog_id="dog-2", user_id="user-1", name="Peanut"),
        }

    def create_profile(self, request):
        self.created_name = request.name
        self.created_user_id = request.user_id
        return CreateDogProfileOutput(
            dog_id="dog-1",
            profile_summary="DouDou",
            created_at="2026-03-25T00:00:00Z",
        )

    def load_profile(self, dog_id: str, *, requesting_user_id: str):
        self.last_load_request = (dog_id, requesting_user_id)
        if dog_id == "missing":
            return None
        if dog_id == "forbidden":
            raise AuthorizationError("Forbidden")
        profile = self.profiles.get(dog_id)
        if profile is not None:
            return profile.model_copy(update={"user_id": requesting_user_id})
        return DogProfile(dog_id=dog_id, user_id=requesting_user_id, name="DouDou")

    def list_profiles(self, *, requesting_user_id: str):
        return [
            profile
            for profile in self.profiles.values()
            if profile.user_id == requesting_user_id
        ]

    def enrich_profile(self, request, extraction_result):
        self.last_enrich_request = request
        self.last_extraction_result = extraction_result
        return EnrichDogProfileOutput(
            updated_fields={"breed": "Corgi"},
            raw_note=None,
            extraction_strategy_used=extraction_result.strategy_used,
        )

    def delete_profile(self, dog_id: str) -> None:
        self.deleted_dog_ids.append(dog_id)


class FakeUserIdentityResolver:
    def __init__(
        self,
        *,
        platform_identity: ResolvedPlatformIdentity | None = None,
        platform_identities: dict[tuple[str, str], ResolvedPlatformIdentity] | None = None,
        account: ResolvedUserAccount | None = None,
        register_identity: ResolvedPlatformIdentity | None = None,
    ) -> None:
        self.platform_identity = platform_identity
        self.platform_identities = dict(platform_identities or {})
        self.register_identity = register_identity or platform_identity
        self.account = account or ResolvedUserAccount(
            user_id="user-1",
            status="pending",
            role="owner",
        )
        self.registered_firebase_uid: str | None = None
        self.activated_user_id: str | None = None
        self.upsert_calls: list[tuple[str, str, str, str]] = []
        self.disconnect_calls: list[tuple[str, str]] = []
        self.ensure_calls: list[tuple[str, str]] = []

    def load_user(self, _user_id: str):
        return self.account

    def resolve_platform_identity(self, *, platform: str, platform_user_id: str):
        explicit_identity = self.platform_identities.get((platform, platform_user_id))
        if explicit_identity is not None:
            return explicit_identity
        if self.platform_identity is None:
            return None
        if (
            self.platform_identity.platform == platform
            and self.platform_identity.platform_user_id == platform_user_id
        ):
            return self.platform_identity
        return None

    def register_web_user(self, *, firebase_uid: str, role: str = "owner"):
        del role
        self.registered_firebase_uid = firebase_uid
        if self.register_identity is None:
            raise AssertionError("platform_identity must be configured")
        return self.register_identity

    def activate_user(self, *, user_id: str):
        self.activated_user_id = user_id
        return ResolvedUserAccount(
            user_id=user_id,
            status="active",
            role=self.account.role,
        )

    def ensure_active_platform_user(self, *, platform: str, platform_user_id: str):
        self.ensure_calls.append((platform, platform_user_id))
        identity = self.resolve_platform_identity(
            platform=platform,
            platform_user_id=platform_user_id,
        )
        if identity is not None:
            return identity, False
        return (
            ResolvedPlatformIdentity(
                user_id="user-1",
                status="active",
                role="owner",
                platform=platform,
                platform_user_id=platform_user_id,
                connection_status="active",
            ),
            True,
        )

    def upsert_platform_connection(
        self,
        *,
        user_id: str,
        platform: str,
        platform_user_id: str,
        status: str,
    ):
        self.upsert_calls.append((user_id, platform, platform_user_id, status))
        return ResolvedPlatformIdentity(
            user_id=user_id,
            status="active",
            role="owner",
            platform=platform,
            platform_user_id=platform_user_id,
            connection_status=status,
        )

    def disconnect_platform_connection(self, *, user_id: str, platform: str):
        self.disconnect_calls.append((user_id, platform))
        return ResolvedPlatformIdentity(
            user_id=user_id,
            status="active",
            role="owner",
            platform=platform,
            platform_user_id=f"{platform}-user",
            connection_status="disconnected",
        )


class FakeUserPrivacyService:
    def __init__(self) -> None:
        self.export_calls: list[str] = []
        self.delete_calls: list[str] = []

    def export_user_data(self, *, user_id: str) -> dict[str, object]:
        self.export_calls.append(user_id)
        return {
            "user": {"user_id": user_id, "status": "active", "role": "owner"},
            "platform_connections": [{"platform": "web", "platform_user_id": user_id}],
            "dog_profiles": [{"id": "dog-1", "name": "DouDou"}],
            "profile_enrichment_log": [],
            "media_assets": [{"media_id": "media-1"}],
            "conversation_sessions": [{"session_id": "user-1__web__session-1"}],
            "public_query_rate_limit_events": [{"user_id": user_id}],
            "format_version": "v1",
            "exported_at": "2026-03-29T00:00:00+00:00",
        }

    def delete_user_data(self, *, user_id: str) -> dict[str, object]:
        self.delete_calls.append(user_id)
        return {
            "deleted": True,
            "user_id": user_id,
            "deleted_at": "2026-03-29T00:00:00+00:00",
            "counts": {
                "platform_connections": 1,
                "dog_profiles": 1,
                "profile_enrichment_log": 0,
                "media_assets": 1,
                "conversation_sessions": 1,
                "public_query_rate_limit_events": 1,
            },
            "blob_objects_deleted": 1,
            "firebase_user_deleted": True,
        }


def build_exif_jpeg() -> bytes:
    image = Image.new("RGB", (4, 4), color="blue")
    exif = Image.Exif()
    exif[271] = "GatewayCam"
    exif[272] = "Model-G"
    buffer = BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def build_test_app(
    *,
    cursor: FakeCursor,
    dog_profile_db_adapter: FakeDogProfileDBAdapter,
    require_auth: bool = False,
    max_upload_bytes: int | None = None,
    enable_bridge_query: bool = False,
    user_identity_resolver: FakeUserIdentityResolver | None = None,
    user_privacy_service: FakeUserPrivacyService | None = None,
    public_query_rate_limiter: InMemorySlidingWindowRateLimiter | None = None,
    agent_query_handler: Callable[[dict[str, object]], dict[str, object]] | None = None,
    agent_stream_query_handler: Callable[[dict[str, object]], object] | None = None,
    metrics_registry: MetricsRegistry | None = None,
    knowledge_embedding_client: object | None = None,
):
    return create_app(
        blob_store=FakeBlobStore(),
        db_connection_factory=lambda: FakeConnection(cursor),
        dog_profile_db_adapter=dog_profile_db_adapter,
        user_identity_resolver=user_identity_resolver,
        user_privacy_service=user_privacy_service,
        public_query_rate_limiter=public_query_rate_limiter,
        knowledge_embedding_client=knowledge_embedding_client,
        agent_query_handler=agent_query_handler,
        agent_stream_query_handler=agent_stream_query_handler,
        enable_bridge_query=enable_bridge_query,
        ffmpeg_binary="ffmpeg",
        auth_verifier=fake_auth_verifier if require_auth else None,
        allowed_callers={WRITER_EMAIL} if require_auth else None,
        auth_audience="https://tailmate-db-gateway.test" if require_auth else None,
        require_auth=require_auth,
        max_upload_bytes=max_upload_bytes,
        metrics_registry=metrics_registry,
    )


def build_public_test_app(
    *,
    public_allowed_origins: tuple[str, ...] = ("https://tailmate-app.vercel.app",),
    public_app_base_url: str = "https://tailmate-app.vercel.app",
):
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="firebase-uid",
            connection_status="active",
        ),
        register_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="firebase-uid",
            connection_status="active",
        ),
        account=ResolvedUserAccount(user_id="user-1", status="active", role="owner"),
    )
    return create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "firebase-uid"},
        agent_query_handler=lambda payload: {
            "session_id": payload["session_id"],
            "response": "ok",
            "metadata": {},
            "error": None,
        },
        public_allowed_origins=public_allowed_origins,
        public_app_base_url=public_app_base_url,
    )


def test_gateway_upload_endpoint_sanitizes_image_and_persists_media_asset() -> None:
    cursor = FakeCursor(session_rows={"session-1": {"dog_id": "dog-1"}})
    dog_profile_db_adapter = FakeDogProfileDBAdapter()
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=dog_profile_db_adapter,
        require_auth=True,
    )
    client = app.test_client()

    response = client.post(
        "/media/upload",
        data={
            "dog_id": "dog-1",
            "resource_kind": "images",
            "session_id": "session-1",
            "file": (BytesIO(build_exif_jpeg()), "../../evil photo.jpg", "image/jpeg"),
        },
        headers=build_auth_headers(),
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["media_ref"] == payload["resource_uri"]
    assert payload["session_id"] == "session-1"
    assert payload["filename"] == secure_filename("../../evil photo.jpg")
    assert dog_profile_db_adapter.last_load_request == ("dog-1", "user-1")

    insert_params = next(
        params for statement, params in cursor.statements if "INSERT INTO media_assets" in statement
    )
    assert insert_params is not None
    assert insert_params[6] == secure_filename("../../evil photo.jpg")
    assert insert_params[9] == WRITER_EMAIL

    blob_store = app.config["BLOB_STORE"]
    stored_payload = blob_store.payloads[payload["logical_path"]][1]
    with Image.open(BytesIO(stored_payload)) as sanitized:
        assert dict(sanitized.getexif()) == {}


def test_gateway_health_reports_database_status() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
    )
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "checks": {"db": "ok"},
        "public_query_enabled": False,
        "internal_db_enabled": True,
        "bridge_query_enabled": False,
    }


def test_public_gateway_entrypoints_route_is_not_exposed() -> None:
    app = build_public_test_app()
    client = app.test_client()

    response = client.get("/entrypoints")

    assert response.status_code == 404


def test_public_gateway_register_options_returns_cors_headers_for_allowlisted_origin() -> None:
    app = build_public_test_app()
    client = app.test_client()

    response = client.options(
        PUBLIC_USER_REGISTER_PATH,
        headers={
            "Origin": "https://tailmate-app.vercel.app",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://tailmate-app.vercel.app"
    assert response.headers["Access-Control-Allow-Methods"] == "DELETE, GET, OPTIONS, POST"
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]


def test_gateway_health_returns_503_when_database_probe_fails() -> None:
    app = build_test_app(
        cursor=FailingCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
    )
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["status"] == "error"
    assert response.get_json()["checks"] == {"db": "error"}
    assert response.get_json()["errors"]["db"] == "database unavailable"


def test_gateway_public_agent_query_rejects_overlong_messages() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    response = client.post(
        PUBLIC_AGENT_QUERY_PATH,
        json={
            "message": "x" * (MAX_QUERY_MESSAGE_LENGTH + 1),
        },
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 400
    assert "at most 4000 characters" in response.get_json()["error"]


def test_gateway_public_agent_query_returns_429_when_user_exceeds_rate_limit() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )
    limiter = InMemorySlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        public_query_rate_limiter=limiter,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused", "metadata": {}, "error": None},
    )
    client = app.test_client()

    first_response = client.post(
        PUBLIC_AGENT_QUERY_PATH,
        json={"message": "hello"},
        headers={"Authorization": "Bearer good-token"},
    )
    second_response = client.post(
        PUBLIC_AGENT_QUERY_PATH,
        json={"message": "hello again"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.headers["Retry-After"] == "60"
    assert second_response.headers["X-RateLimit-Limit"] == "1"
    assert second_response.headers["X-RateLimit-Remaining"] == "0"


def test_gateway_public_agent_query_ignores_unknown_fields() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )
    captured_payload: dict[str, object] = {}

    def fake_query_handler(payload: dict[str, object]) -> dict[str, object]:
        captured_payload.update(payload)
        return {
            "session_id": str(payload["session_id"]),
            "response": "ok",
            "metadata": {},
            "error": None,
        }

    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=fake_query_handler,
    )
    client = app.test_client()

    response = client.post(
        PUBLIC_AGENT_QUERY_PATH,
        json={
            "message": "hello",
            "unexpected_future_field": "ignore-me",
        },
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["response"] == "ok"
    metadata = captured_payload["metadata"]
    assert isinstance(metadata, dict)
    assert "unexpected_future_field" not in metadata


def test_gateway_user_export_returns_owner_scoped_snapshot() -> None:
    resolver = FakeUserIdentityResolver()
    privacy_service = FakeUserPrivacyService()
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        user_privacy_service=privacy_service,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    response = client.get(
        USER_EXPORT_PATH,
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["format_version"] == "v1"
    assert privacy_service.export_calls == ["user-1"]


def test_gateway_user_delete_requires_matching_firebase_identity() -> None:
    resolver = FakeUserIdentityResolver()
    privacy_service = FakeUserPrivacyService()
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        user_privacy_service=privacy_service,
        firebase_token_verifier=lambda _token: {"uid": "user-2"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    response = client.delete(
        USER_DELETE_PATH,
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 403
    assert response.get_json()["error"] == "User does not own the requested user account."
    assert privacy_service.delete_calls == []


def test_gateway_user_delete_returns_deletion_summary() -> None:
    resolver = FakeUserIdentityResolver()
    privacy_service = FakeUserPrivacyService()
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        user_privacy_service=privacy_service,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    response = client.delete(
        USER_DELETE_PATH,
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["deleted"] is True
    assert privacy_service.delete_calls == ["user-1"]


def test_gateway_rejects_oversized_uploads_with_413() -> None:
    cursor = FakeCursor(session_rows={"session-1": {"dog_id": "dog-1"}})
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        max_upload_bytes=64,
    )
    client = app.test_client()

    response = client.post(
        "/media/upload",
        data={
            "dog_id": "dog-1",
            "resource_kind": "images",
            "session_id": "session-1",
            "file": (BytesIO(b"x" * 256), "large.jpg", "image/jpeg"),
        },
        headers=build_auth_headers(),
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert "64-byte limit" in response.get_json()["error"]


def test_gateway_rejects_image_uploads_over_kind_limit_with_413(monkeypatch) -> None:
    monkeypatch.setattr(contract_types, "DEFAULT_IMAGE_UPLOAD_BYTES", 64)
    cursor = FakeCursor(session_rows={"session-1": {"dog_id": "dog-1"}})
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        max_upload_bytes=256,
    )
    client = app.test_client()

    response = client.post(
        "/media/upload",
        data={
            "dog_id": "dog-1",
            "resource_kind": "images",
            "session_id": "session-1",
            "file": (BytesIO(b"x" * 65), "photo.jpg", "image/jpeg"),
        },
        headers=build_auth_headers(),
        content_type="multipart/form-data",
    )

    assert response.status_code == 413


def test_gateway_dog_profile_endpoints_delegate_to_business_adapter() -> None:
    cursor = FakeCursor()
    dog_profile_db_adapter = FakeDogProfileDBAdapter()
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=dog_profile_db_adapter,
        require_auth=False,
    )
    client = app.test_client()

    create_response = client.post(
        "/dog-profiles",
        json={"name": "DouDou", "session_id": "session-1", "user_id": "user-1"},
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
    )
    load_response = client.get(
        "/dog-profiles/dog-1",
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
    )
    enrich_response = client.post(
        "/dog-profiles/dog-1/enrich",
        json={
            "requesting_user_id": "ignored-by-gateway",
            "user_message": "DouDou is a corgi",
            "extraction_result": {
                "structured_fields": {"breed": "Corgi"},
                "raw_note": None,
                "confidence": 0.9,
                "strategy_used": "rule",
            },
        },
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
    )

    assert create_response.status_code == 201
    assert create_response.get_json()["dog_id"] == "dog-1"
    assert dog_profile_db_adapter.created_name == "DouDou"
    assert dog_profile_db_adapter.created_user_id == "user-1"
    assert cursor.session_rows["session-1"]["dog_id"] == "dog-1"
    assert load_response.get_json()["profile"]["name"] == "DouDou"
    assert dog_profile_db_adapter.last_load_request == ("dog-1", "user-1")
    assert dog_profile_db_adapter.last_enrich_request.requesting_user_id == "user-1"
    assert enrich_response.get_json()["updated_fields"]["breed"] == "Corgi"


def test_gateway_lists_owner_scoped_dog_profiles() -> None:
    dog_profile_db_adapter = FakeDogProfileDBAdapter()
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=dog_profile_db_adapter,
        require_auth=False,
    )
    client = app.test_client()

    response = client.get(
        "/dog-profiles",
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
    )

    assert response.status_code == 200
    assert [profile["name"] for profile in response.get_json()["profiles"]] == [
        "DouDou",
        "Peanut",
    ]


def test_gateway_list_dog_profiles_requires_internal_bearer_auth_when_enabled() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
    )
    client = app.test_client()

    response = client.get(
        "/dog-profiles",
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Authorization bearer token is required."


def test_gateway_knowledge_search_endpoint_returns_ranked_hits() -> None:
    cursor = FakeCursor(
        fetchall_result=[
            (
                "Feed adult dogs twice daily.",
                "Tailmate Feeding Guide",
                "nutrition",
                "en-AU",
                0.91,
            ),
            (
                "Change water daily.",
                "Tailmate Feeding Guide",
                "hydration",
                "en-AU",
                0.87,
            ),
        ]
    )
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
    )
    client = app.test_client()

    response = client.post(
        "/knowledge/search",
        json={"embedding": [0.1, 0.2, 0.3], "locale": "en-AU", "top_k": 2},
    )

    assert response.status_code == 200
    assert response.get_json()["hits"][0]["source_label"] == "Tailmate Feeding Guide"
    statement, params = cursor.statements[0]
    assert "FROM knowledge_chunks" in statement
    assert "ORDER BY embedding <=> %s::vector" in statement
    assert params == ["[0.1,0.2,0.3]", "en-AU", "[0.1,0.2,0.3]", 2]


def test_gateway_knowledge_search_endpoint_validates_request_shape() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
    )
    client = app.test_client()

    response = client.post(
        "/knowledge/search",
        json={"embedding": "not-a-vector", "locale": "en-AU"},
    )

    assert response.status_code == 400
    assert "embedding" in response.get_json()["error"]


def test_gateway_kb_chunk_create_endpoint_returns_created_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        gateway_app,
        "create_knowledge_chunk_record",
        lambda _engine_factory, *, payload, embedding_client: {
            "chunk": {**payload.model_dump(mode="json"), "id": "chunk-1"},
            "embedding_dimensions": 768,
            "embedding_client": str(type(embedding_client).__name__),
        },
    )
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
        knowledge_embedding_client=object(),
    )
    client = app.test_client()

    response = client.post(
        "/kb/chunks",
        json={
            "content": "Feed adult dogs twice daily.",
            "source_label": "Feeding Guide",
            "category": "nutrition",
            "locale": "en-AU",
        },
    )

    assert response.status_code == 201
    assert response.get_json()["chunk"]["id"] == "chunk-1"
    assert response.get_json()["embedding_dimensions"] == 768


def test_gateway_kb_chunk_preview_endpoint_returns_serialized_hits(monkeypatch) -> None:
    monkeypatch.setattr(
        gateway_app,
        "preview_knowledge_chunk_records",
        lambda _engine_factory, *, payload, embedding_client: [
            KnowledgeSearchHit(
                content="Feed adult dogs twice daily.",
                source_label="Feeding Guide",
                category="nutrition",
                locale=payload.locale,
                score=0.91,
            )
        ],
    )
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
        knowledge_embedding_client=object(),
    )
    client = app.test_client()

    response = client.get("/kb/chunks?query=feeding&locale=en-AU&top_k=2")

    assert response.status_code == 200
    assert response.get_json() == {
        "query": "feeding",
        "locale": "en-AU",
        "top_k": 2,
        "hits": [
            {
                "content": "Feed adult dogs twice daily.",
                "source_label": "Feeding Guide",
                "category": "nutrition",
                "locale": "en-AU",
                "score": 0.91,
            }
        ],
    }


def test_gateway_kb_chunk_delete_endpoint_returns_deleted_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        gateway_app,
        "delete_knowledge_chunk_record",
        lambda _engine_factory, *, chunk_id: {"deleted": True, "chunk_id": chunk_id},
    )
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
    )
    client = app.test_client()

    response = client.delete("/kb/chunks/chunk-9")

    assert response.status_code == 200
    assert response.get_json() == {"deleted": True, "chunk_id": "chunk-9"}


def test_gateway_metrics_endpoint_exposes_prometheus_text() -> None:
    metrics_registry = reset_metrics_registry()
    record_session_started(channel="web")
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=False,
        metrics_registry=metrics_registry,
    )
    client = app.test_client()

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/plain; version=0.0.4")
    body = response.get_data(as_text=True)
    assert "# HELP tailmate_sessions_total" in body
    assert 'tailmate_sessions_total{channel="web"} 1' in body


def test_format_sse_event_uses_a_blank_line_frame_separator() -> None:
    event = gateway_app.format_sse_event(
        {
            "event": "query.delta",
            "session_id": "session-1",
            "delta": "Hello",
        }
    )

    assert event == (
        'event: query.delta\n'
        'data: {"event":"query.delta","session_id":"session-1","delta":"Hello"}\n\n'
    )


def test_gateway_public_agent_query_validates_firebase_and_rewrites_session_ids() -> None:
    captured: dict[str, object] = {}
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )

    def fake_agent_query_handler(payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "session_id": payload["session_id"],
            "response": "ok",
            "metadata": {"dog_id": "dog-1"},
            "error": None,
        }

    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda token: {"uid": "user-1"} if token == "good-token" else {},
        agent_query_handler=fake_agent_query_handler,
    )
    client = app.test_client()

    response = client.post(
        PUBLIC_AGENT_QUERY_PATH,
        json={
            "session_id": "client-session",
            "message": "hello",
            "dog_id": "dog-1",
            STRIP_METADATA_REQUEST_METADATA_KEY: {
                "dog_id": "dog-1",
                "resource_kind": "images",
                "filename": "sample.jpg",
                "content_type": "image/jpeg",
                "payload_base64": "c2FtcGxl",
            },
        },
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    assert response.get_json()["session_id"] == "client-session"
    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.headers[TRACE_ID_HEADER]
    assert captured["payload"]["session_id"] == "user-1__web__client-session"
    assert captured["payload"]["message"] == "hello"
    metadata = captured["payload"]["metadata"]
    assert metadata["user_id"] == "user-1"
    assert metadata["request_id"] == request_id
    assert metadata["trace_id"] == response.headers[TRACE_ID_HEADER]
    assert metadata["channel"] == "web"
    assert metadata["dog_id"] == "dog-1"
    assert metadata["traceparent"].startswith("00-")
    assert metadata[STRIP_METADATA_REQUEST_METADATA_KEY] == {
        "dog_id": "dog-1",
        "resource_kind": "images",
        "filename": "sample.jpg",
        "content_type": "image/jpeg",
        "payload_base64": "c2FtcGxl",
        "session_id": "user-1__web__client-session",
    }


def test_gateway_public_agent_query_ignores_unknown_fields_for_forward_compatibility() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )
    captured: dict[str, object] = {}

    def fake_query_handler(payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "session_id": str(payload["session_id"]),
            "response": "ok",
            "metadata": {},
            "error": None,
        }

    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=fake_query_handler,
    )
    client = app.test_client()

    response = client.post(
        PUBLIC_AGENT_QUERY_PATH,
        json={
            "message": "hello",
            "future_field": "ignored",
        },
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    forwarded_payload = captured["payload"]
    assert isinstance(forwarded_payload, dict)
    assert "future_field" not in forwarded_payload


def test_gateway_public_agent_query_blocks_missing_or_inactive_users() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="pending",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )

    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "should not run"},
    )
    client = app.test_client()

    response = client.post(
        PUBLIC_AGENT_QUERY_PATH,
        json={"message": "hello"},
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 403


def test_gateway_register_user_creates_pending_master_account_with_active_web_connection() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=None,
        register_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="pending",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    response = client.post(
        PUBLIC_USER_REGISTER_PATH,
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 201
    assert resolver.registered_firebase_uid == "user-1"
    assert response.get_json()["user"]["status"] == "pending"
    assert response.get_json()["connection"]["connection_status"] == "active"


def test_gateway_activate_user_transitions_pending_account_to_active() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="pending",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        ),
        account=ResolvedUserAccount(user_id="user-1", status="pending", role="owner"),
    )
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    response = client.post(
        PUBLIC_USER_ACTIVATE_PATH,
        headers={"Authorization": "Bearer good-token"},
    )

    assert response.status_code == 200
    assert resolver.activated_user_id == "user-1"
    assert response.get_json()["user"]["status"] == "active"


def test_gateway_lifecycle_routes_accept_lowercase_bearer_scheme() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="pending",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        ),
        register_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="pending",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        ),
    )
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    register_response = client.post(
        PUBLIC_USER_REGISTER_PATH,
        headers={"Authorization": "bearer good-token"},
    )
    activate_response = client.post(
        PUBLIC_USER_ACTIVATE_PATH,
        headers={"Authorization": "bearer good-token"},
    )

    assert register_response.status_code == 200
    assert activate_response.status_code == 200


def test_gateway_connection_routes_manage_non_web_platform_bindings() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identity=ResolvedPlatformIdentity(
            user_id="user-1",
            status="active",
            role="owner",
            platform="web",
            platform_user_id="user-1",
            connection_status="active",
        )
    )
    app = create_app(
        enable_public_query=True,
        enable_internal_db=False,
        user_identity_resolver=resolver,
        firebase_token_verifier=lambda _token: {"uid": "user-1"},
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    connect_response = client.post(
        TELEGRAM_CONNECTION_PATH,
        json={"platform_user_id": "telegram-user-1", "status": "active"},
        headers={"Authorization": "Bearer good-token"},
    )
    disconnect_response = client.delete(
        TELEGRAM_CONNECTION_PATH,
        headers={"Authorization": "Bearer good-token"},
    )

    assert connect_response.status_code == 200
    assert resolver.upsert_calls == [("user-1", "telegram", "telegram-user-1", "active")]
    assert connect_response.get_json()["connection"]["platform"] == "telegram"
    assert disconnect_response.status_code == 200
    assert resolver.disconnect_calls == [("user-1", "telegram")]
    assert disconnect_response.get_json()["connection"]["connection_status"] == "disconnected"


def test_gateway_bridge_query_resolves_platform_identity_and_namespaces_session() -> None:
    captured: dict[str, object] = {}
    resolver = FakeUserIdentityResolver(
        platform_identities={
            (
                "telegram",
                "tg-42",
            ): ResolvedPlatformIdentity(
                user_id="user-1",
                status="active",
                role="owner",
                platform="telegram",
                platform_user_id="tg-42",
                connection_status="active",
            )
        }
    )

    def fake_agent_query_handler(payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "session_id": payload["session_id"],
            "response": "ok",
            "metadata": {"dog_id": "dog-1"},
            "error": None,
        }

    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        enable_bridge_query=True,
        user_identity_resolver=resolver,
        agent_query_handler=fake_agent_query_handler,
    )
    client = app.test_client()

    response = client.post(
        "/bridge/query",
        json={
            "platform": "telegram",
            "platform_user_id": "tg-42",
            "session_id": "bridge-session",
            "message": "hello",
            "dog_id": "dog-1",
        },
        headers=build_auth_headers(),
    )

    assert response.status_code == 200
    assert response.get_json()["session_id"] == "bridge-session"
    request_id = response.headers[REQUEST_ID_HEADER]
    assert response.headers[TRACE_ID_HEADER]
    assert captured["payload"]["session_id"] == "user-1__telegram__bridge-session"
    assert captured["payload"]["message"] == "hello"
    metadata = captured["payload"]["metadata"]
    assert metadata["user_id"] == "user-1"
    assert metadata["request_id"] == request_id
    assert metadata["trace_id"] == response.headers[TRACE_ID_HEADER]
    assert metadata["channel"] == "telegram"
    assert metadata["dog_id"] == "dog-1"
    assert metadata["traceparent"].startswith("00-")


def test_gateway_bridge_user_ensure_provisions_or_reuses_non_web_identities() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identities={
            (
                "telegram",
                "tg-42",
            ): ResolvedPlatformIdentity(
                user_id="user-1",
                status="active",
                role="owner",
                platform="telegram",
                platform_user_id="tg-42",
                connection_status="active",
            )
        },
        account=ResolvedUserAccount(user_id="user-1", status="active", role="owner"),
    )
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        enable_bridge_query=True,
        user_identity_resolver=resolver,
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    existing_response = client.post(
        "/bridge/users/ensure",
        json={"platform": "telegram", "platform_user_id": "tg-42"},
        headers=build_auth_headers(),
    )
    created_response = client.post(
        "/bridge/users/ensure",
        json={"platform": "messenger", "platform_user_id": "messenger-42"},
        headers=build_auth_headers(),
    )

    assert existing_response.status_code == 200
    assert existing_response.get_json()["created"] is False
    assert created_response.status_code == 201
    assert created_response.get_json()["created"] is True
    assert resolver.ensure_calls == [
        ("telegram", "tg-42"),
        ("messenger", "messenger-42"),
    ]


def test_gateway_bridge_query_rejects_inactive_or_invalid_platform_bindings() -> None:
    inactive_resolver = FakeUserIdentityResolver(
        platform_identities={
            (
                "telegram",
                "tg-42",
            ): ResolvedPlatformIdentity(
                user_id="user-1",
                status="pending",
                role="owner",
                platform="telegram",
                platform_user_id="tg-42",
                connection_status="active",
            ),
            (
                "telegram",
                "tg-43",
            ): ResolvedPlatformIdentity(
                user_id="user-1",
                status="active",
                role="owner",
                platform="telegram",
                platform_user_id="tg-43",
                connection_status="disconnected",
            ),
        }
    )
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        enable_bridge_query=True,
        user_identity_resolver=inactive_resolver,
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    pending_response = client.post(
        "/bridge/query",
        json={"platform": "telegram", "platform_user_id": "tg-42", "message": "hello"},
        headers=build_auth_headers(),
    )
    disconnected_response = client.post(
        "/bridge/query",
        json={"platform": "telegram", "platform_user_id": "tg-43", "message": "hello"},
        headers=build_auth_headers(),
    )
    unsupported_response = client.post(
        "/bridge/query",
        json={"platform": "web", "platform_user_id": "user-1", "message": "hello"},
        headers=build_auth_headers(),
    )
    unsupported_platform_response = client.post(
        "/bridge/query",
        json={"platform": "slack", "platform_user_id": "slack-1", "message": "hello"},
        headers=build_auth_headers(),
    )

    assert pending_response.status_code == 403
    assert disconnected_response.status_code == 403
    assert unsupported_response.status_code == 400
    assert unsupported_platform_response.status_code == 403


def test_gateway_bridge_query_returns_error_payload_when_agent_handler_raises() -> None:
    resolver = FakeUserIdentityResolver(
        platform_identities={
            (
                "telegram",
                "tg-42",
            ): ResolvedPlatformIdentity(
                user_id="user-1",
                status="active",
                role="owner",
                platform="telegram",
                platform_user_id="tg-42",
                connection_status="active",
            )
        }
    )

    def exploding_handler(payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("Vertex AI Agent Engine timeout")

    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        enable_bridge_query=True,
        user_identity_resolver=resolver,
        agent_query_handler=exploding_handler,
    )
    client = app.test_client()

    response = client.post(
        "/bridge/query",
        json={
            "platform": "telegram",
            "platform_user_id": "tg-42",
            "session_id": "test-session",
            "message": "hello",
        },
        headers=build_auth_headers(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["response"] == ""
    assert payload["error"]["type"] == "InternalError"
    assert payload["session_id"] == "test-session"


def test_gateway_bridge_query_route_is_disabled_when_flag_is_off() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        enable_bridge_query=False,
        user_identity_resolver=FakeUserIdentityResolver(),
        agent_query_handler=lambda _payload: {"response": "unused"},
    )
    client = app.test_client()

    response = client.post(
        "/bridge/query",
        json={"platform": "telegram", "platform_user_id": "tg-42", "message": "hello"},
        headers=build_auth_headers(),
    )

    assert response.status_code == 404


def test_gateway_bridge_webhook_claim_is_atomic_for_duplicate_message_ids() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        enable_bridge_query=True,
        user_identity_resolver=FakeUserIdentityResolver(),
        agent_query_handler=lambda _payload: {"response": "unused", "metadata": {}, "error": None},
    )
    client = app.test_client()

    first = client.post(
        "/bridge/webhooks/claim",
        json={"message_id": "wamid-1"},
        headers=build_auth_headers(),
    )
    second = client.post(
        "/bridge/webhooks/claim",
        json={"message_id": "wamid-1"},
        headers=build_auth_headers(),
    )

    assert first.status_code == 201
    assert first.get_json() == {"claimed": True}
    assert second.status_code == 200
    assert second.get_json() == {"claimed": False}


def test_gateway_bridge_webhook_release_removes_processed_message_id() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
        enable_bridge_query=True,
        user_identity_resolver=FakeUserIdentityResolver(),
        agent_query_handler=lambda _payload: {"response": "unused", "metadata": {}, "error": None},
    )
    client = app.test_client()

    claimed = client.post(
        "/bridge/webhooks/claim",
        json={"message_id": "wamid-1"},
        headers=build_auth_headers(),
    )
    released = client.post(
        "/bridge/webhooks/release",
        json={"message_id": "wamid-1"},
        headers=build_auth_headers(),
    )
    reclaimed = client.post(
        "/bridge/webhooks/claim",
        json={"message_id": "wamid-1"},
        headers=build_auth_headers(),
    )

    assert claimed.status_code == 201
    assert released.status_code == 200
    assert released.get_json() == {"released": True}
    assert reclaimed.status_code == 201
    assert reclaimed.get_json() == {"claimed": True}


def test_gateway_rejects_missing_bearer_token() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
    )
    client = app.test_client()

    response = client.post(
        "/dog-profiles",
        json={"name": "DouDou", "session_id": "session-1", "user_id": "user-1"},
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
    )

    assert response.status_code == 401
    assert response.get_json()["error"] == "Authorization bearer token is required."


def test_gateway_rejects_write_calls_from_non_allowlisted_caller() -> None:
    app = build_test_app(
        cursor=FakeCursor(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
    )
    client = app.test_client()

    response = client.post(
        "/dog-profiles",
        json={"name": "DouDou", "session_id": "session-1", "user_id": "user-1"},
        headers=build_auth_headers("reader-token"),
    )

    assert response.status_code == 403
    assert "not allowed" in response.get_json()["error"]


def test_gateway_rejects_dog_access_when_session_is_bound_to_another_profile() -> None:
    cursor = FakeCursor(session_rows={"session-1": {"dog_id": "dog-2"}})
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
    )
    client = app.test_client()

    response = client.post(
        "/media/upload",
        data={
            "dog_id": "dog-1",
            "resource_kind": "images",
            "session_id": "session-1",
            "file": (BytesIO(build_exif_jpeg()), "photo.jpg", "image/jpeg"),
        },
        headers=build_auth_headers(),
        content_type="multipart/form-data",
    )

    assert response.status_code == 403
    assert "not authorized" in response.get_json()["error"]


def test_gateway_save_session_returns_authorization_errors_as_403() -> None:
    cursor = FakeCursor(session_rows={"session-1": {"dog_id": "dog-1"}})
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
        require_auth=True,
    )
    client = app.test_client()

    response = client.put(
        "/sessions/session-1",
        json={
            "turns": [],
            "attributes": {"dog_id": "dog-2"},
        },
        headers=build_auth_headers(user_id=None),
    )

    assert response.status_code == 403
    assert "cannot be rebound" in response.get_json()["error"]


def test_gateway_deletes_created_profile_when_session_binding_fails(monkeypatch) -> None:
    cursor = FakeCursor()
    dog_profile_db_adapter = FakeDogProfileDBAdapter()
    app = build_test_app(
        cursor=cursor,
        dog_profile_db_adapter=dog_profile_db_adapter,
        require_auth=False,
    )
    client = app.test_client()

    def fail_bind(*args, **kwargs) -> None:
        del args, kwargs
        raise RuntimeError("bind failed")

    monkeypatch.setattr(gateway_app, "bind_session_to_dog", fail_bind)

    response = client.post(
        "/dog-profiles",
        json={"name": "DouDou", "session_id": "session-1", "user_id": "user-1"},
        headers={TRUSTED_USER_ID_HEADER: "user-1"},
    )

    assert response.status_code == 500
    assert dog_profile_db_adapter.deleted_dog_ids == ["dog-1"]
