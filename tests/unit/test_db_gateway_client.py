from __future__ import annotations

import pytest
import requests

from tailmate.adapters.db_gateway.client import DbGatewayClient
from tailmate.agent_runtime.current_context import (
    RuntimeRequestContext,
    reset_current_context,
    set_current_context,
)
from tailmate.contracts.constants import REQUEST_ID_HEADER, TRACE_ID_HEADER, TRUSTED_USER_ID_HEADER
from tailmate.contracts.errors import AdapterError
from tailmate.observability import LogContext, reset_log_context, set_log_context


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text
        self.reason = "error" if status_code >= 400 else "ok"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(response=self)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def request(
        self,
        method: str,
        url: str,
        json=None,
        data=None,
        files=None,
        headers=None,
        timeout: int | None = None,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "json": json,
                "data": data,
                "files": files,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return self.responses.pop(0)


def test_db_gateway_client_loads_and_saves_sessions() -> None:
    session = FakeSession(
        [
            FakeResponse({"session_id": "session/1", "turns": [], "attributes": {}}),
            FakeResponse({"saved": True}),
        ]
    )
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app/",
        timeout_seconds=12,
        session=session,
    )

    payload = client.load_session("session/1")
    client.save_session("session/1", turns=[{"role": "user", "message": "hi"}], attributes={})

    assert payload == {"session_id": "session/1", "turns": [], "attributes": {}}
    assert session.calls == [
        {
            "method": "GET",
            "url": "https://tailmate-db-gateway-abc.a.run.app/sessions/session%2F1",
            "json": None,
            "data": None,
            "files": None,
            "headers": None,
            "timeout": 12,
        },
        {
            "method": "PUT",
            "url": "https://tailmate-db-gateway-abc.a.run.app/sessions/session%2F1",
            "json": {
                "turns": [{"role": "user", "message": "hi"}],
                "attributes": {},
            },
            "data": None,
            "files": None,
            "headers": None,
            "timeout": 12,
        },
    ]


def test_db_gateway_client_calls_bridge_auto_provision_and_query_routes() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "created": True,
                    "user": {"user_id": "user-1", "status": "active", "role": "owner"},
                    "connection": {
                        "user_id": "user-1",
                        "status": "active",
                        "role": "owner",
                        "platform": "messenger",
                        "platform_user_id": "+5511999999999",
                        "connection_status": "active",
                    },
                }
            ),
            FakeResponse({"claimed": True}),
            FakeResponse(
                {
                    "session_id": "chat-1",
                    "response": "Hello there",
                    "metadata": {},
                    "error": None,
                }
            ),
        ]
    )
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=15,
        session=session,
    )

    ensure_payload = client.ensure_platform_user(
        platform="messenger",
        platform_user_id="+5511999999999",
    )
    claimed = client.claim_webhook_event(message_id="wamid-1")
    query_payload = client.bridge_query(
        platform="messenger",
        platform_user_id="+5511999999999",
        message="hello",
        session_id="chat-1",
    )

    assert ensure_payload["created"] is True
    assert claimed is True
    assert query_payload["response"] == "Hello there"
    assert session.calls == [
        {
            "method": "POST",
            "url": "https://tailmate-db-gateway-abc.a.run.app/bridge/users/ensure",
            "json": {
                "platform": "messenger",
                "platform_user_id": "+5511999999999",
            },
            "data": None,
            "files": None,
            "headers": None,
            "timeout": 15,
        },
        {
            "method": "POST",
            "url": "https://tailmate-db-gateway-abc.a.run.app/bridge/webhooks/claim",
            "json": {"message_id": "wamid-1"},
            "data": None,
            "files": None,
            "headers": None,
            "timeout": 15,
        },
        {
            "method": "POST",
            "url": "https://tailmate-db-gateway-abc.a.run.app/bridge/query",
            "json": {
                "platform": "messenger",
                "platform_user_id": "+5511999999999",
                "message": "hello",
                "session_id": "chat-1",
            },
            "data": None,
            "files": None,
            "headers": None,
            "timeout": 15,
        },
    ]


def test_db_gateway_client_releases_webhook_claims() -> None:
    session = FakeSession([FakeResponse({"released": True})])
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=15,
        session=session,
    )

    released = client.release_webhook_event(message_id="wamid-1")

    assert released is True
    assert session.calls == [
        {
            "method": "POST",
            "url": "https://tailmate-db-gateway-abc.a.run.app/bridge/webhooks/release",
            "json": {"message_id": "wamid-1"},
            "data": None,
            "files": None,
            "headers": None,
            "timeout": 15,
        }
    ]


def test_db_gateway_client_surfaces_gateway_errors() -> None:
    session = FakeSession([FakeResponse({"error": "boom"}, status_code=500)])
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        session=session,
    )

    with pytest.raises(AdapterError, match="status 500: boom"):
        client.load_session("session-1")


def test_db_gateway_client_uploads_media_through_multipart_form_data() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
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
                    "session_id": "session-1",
                }
            )
        ]
    )
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=18,
        session=session,
    )

    payload = client.upload_media(
        dog_id="dog-1",
        resource_kind="images",
        filename="sample.jpg",
        content_type="image/jpeg",
        payload=b"clean-image",
        session_id="session-1",
        trusted_user_id="user-1",
    )

    assert payload["resource_uri"] == "gs://tailmate-media/dogs/dog-1/images/sample.jpg"
    assert session.calls == [
        {
            "method": "POST",
            "url": "https://tailmate-db-gateway-abc.a.run.app/media/upload",
            "json": None,
            "data": {
                "dog_id": "dog-1",
                "resource_kind": "images",
                "session_id": "session-1",
            },
            "files": {
                "file": ("sample.jpg", b"clean-image", "image/jpeg"),
            },
            "headers": {TRUSTED_USER_ID_HEADER: "user-1"},
            "timeout": 18,
        }
    ]


def test_db_gateway_client_handles_dog_profile_business_endpoints() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "dog_id": "dog-1",
                    "profile_summary": "DouDou | Corgi",
                    "created_at": "2026-03-25T00:00:00Z",
                }
            ),
            FakeResponse({"found": True, "profile": {"dog_id": "dog-1", "name": "DouDou"}}),
            FakeResponse(
                {
                    "updated_fields": {"breed": "Corgi"},
                    "raw_note": None,
                    "extraction_strategy_used": "rule",
                }
            ),
            FakeResponse({"found": False, "dog_id": "dog-missing"}),
        ]
    )
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=9,
        session=session,
    )

    create_payload = client.create_dog_profile(
        {"name": "DouDou", "session_id": "session-1", "user_id": "user-1"}
    )
    loaded_profile = client.load_dog_profile(
        "dog-1",
        trusted_user_id="user-1",
        session_id="session-1",
    )
    enrich_payload = client.enrich_dog_profile(
        "dog-1",
        {"user_message": "DouDou is a corgi"},
        trusted_user_id="user-1",
        session_id="session-1",
    )
    missing_profile = client.load_dog_profile(
        "dog-missing",
        trusted_user_id="user-1",
        session_id="session-1",
    )

    assert create_payload["dog_id"] == "dog-1"
    assert loaded_profile == {"dog_id": "dog-1", "name": "DouDou"}
    assert enrich_payload["updated_fields"]["breed"] == "Corgi"
    assert missing_profile is None
    assert session.calls[0]["url"].endswith("/dog-profiles")
    assert session.calls[1]["url"].endswith("/dog-profiles/dog-1?session_id=session-1")
    assert session.calls[2]["json"]["session_id"] == "session-1"
    assert session.calls[2]["url"].endswith("/dog-profiles/dog-1/enrich")
    assert session.calls[0]["headers"] == {TRUSTED_USER_ID_HEADER: "user-1"}
    assert session.calls[1]["headers"] == {TRUSTED_USER_ID_HEADER: "user-1"}
    assert session.calls[2]["headers"] == {TRUSTED_USER_ID_HEADER: "user-1"}


def test_db_gateway_client_lists_owner_scoped_dog_profiles() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "profiles": [
                        {"dog_id": "dog-1", "name": "DouDou"},
                        {"dog_id": "dog-2", "name": "Peanut"},
                    ]
                }
            )
        ]
    )
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=9,
        session=session,
    )

    profiles = client.list_dog_profiles(trusted_user_id="user-1")

    assert [profile["name"] for profile in profiles] == ["DouDou", "Peanut"]
    assert session.calls == [
        {
            "method": "GET",
            "url": "https://tailmate-db-gateway-abc.a.run.app/dog-profiles",
            "json": None,
            "data": None,
            "files": None,
            "headers": {TRUSTED_USER_ID_HEADER: "user-1"},
            "timeout": 9,
        }
    ]


def test_db_gateway_client_uses_current_request_context_for_owner_and_session_scope() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
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
                    "session_id": "session-ctx",
                }
            ),
            FakeResponse({"found": True, "profile": {"dog_id": "dog-1", "name": "DouDou"}}),
            FakeResponse(
                {
                    "updated_fields": {"breed": "Corgi"},
                    "raw_note": None,
                    "extraction_strategy_used": "rule",
                }
            ),
        ]
    )
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=11,
        session=session,
    )
    token = set_current_context(
        RuntimeRequestContext(
            session_id="session-ctx",
            metadata={"dog_id": "dog-1", "user_id": "user-ctx"},
            dog_id="dog-1",
            user_id="user-ctx",
        )
    )

    try:
        upload_payload = client.upload_media(
            dog_id="dog-1",
            resource_kind="images",
            filename="sample.jpg",
            content_type="image/jpeg",
            payload=b"clean-image",
        )
        loaded_profile = client.load_dog_profile("dog-1")
        enrich_payload = client.enrich_dog_profile("dog-1", {"user_message": "DouDou is a corgi"})
    finally:
        reset_current_context(token)

    assert upload_payload["session_id"] == "session-ctx"
    assert loaded_profile == {"dog_id": "dog-1", "name": "DouDou"}
    assert enrich_payload["updated_fields"]["breed"] == "Corgi"
    assert session.calls[0]["data"]["session_id"] == "session-ctx"
    assert session.calls[0]["headers"] == {TRUSTED_USER_ID_HEADER: "user-ctx"}
    assert session.calls[1]["url"].endswith("/dog-profiles/dog-1?session_id=session-ctx")
    assert session.calls[1]["headers"] == {TRUSTED_USER_ID_HEADER: "user-ctx"}
    assert session.calls[2]["json"]["session_id"] == "session-ctx"
    assert session.calls[2]["headers"] == {TRUSTED_USER_ID_HEADER: "user-ctx"}


def test_db_gateway_client_searches_verified_knowledge() -> None:
    session = FakeSession(
        [
            FakeResponse(
                {
                    "hits": [
                        {
                            "content": "Feed adult dogs twice daily.",
                            "source_label": "Tailmate Feeding Guide",
                            "category": "nutrition",
                            "locale": "en-AU",
                            "score": 0.91,
                        }
                    ]
                }
            )
        ]
    )
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=7,
        session=session,
    )

    payload = client.search_knowledge(
        embedding=[0.1, 0.2, 0.3],
        locale="en-AU",
        top_k=2,
    )

    assert payload == [
        {
            "content": "Feed adult dogs twice daily.",
            "source_label": "Tailmate Feeding Guide",
            "category": "nutrition",
            "locale": "en-AU",
            "score": 0.91,
        }
    ]
    assert session.calls == [
        {
            "method": "POST",
            "url": "https://tailmate-db-gateway-abc.a.run.app/knowledge/search",
            "json": {
                "embedding": [0.1, 0.2, 0.3],
                "locale": "en-AU",
                "top_k": 2,
            },
            "data": None,
            "files": None,
            "headers": None,
            "timeout": 7,
        }
    ]


def test_db_gateway_client_propagates_request_id_header_from_log_context() -> None:
    session = FakeSession([FakeResponse({"saved": True})])
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=5,
        session=session,
    )
    log_token = set_log_context(LogContext(request_id="req-123"))

    try:
        client.save_session("session-1", turns=[], attributes={})
    finally:
        reset_log_context(log_token)

    assert session.calls == [
        {
            "method": "PUT",
            "url": "https://tailmate-db-gateway-abc.a.run.app/sessions/session-1",
            "json": {
                "turns": [],
                "attributes": {},
            },
            "data": None,
            "files": None,
            "headers": {REQUEST_ID_HEADER: "req-123"},
            "timeout": 5,
        }
    ]


def test_db_gateway_client_propagates_trace_id_header_from_log_context() -> None:
    session = FakeSession([FakeResponse({"saved": True})])
    client = DbGatewayClient(
        gateway_url="https://tailmate-db-gateway-abc.a.run.app",
        timeout_seconds=5,
        session=session,
    )
    log_token = set_log_context(LogContext(trace_id="trace-123"))

    try:
        client.save_session("session-1", turns=[], attributes={})
    finally:
        reset_log_context(log_token)

    assert session.calls[0]["headers"] == {TRACE_ID_HEADER: "trace-123"}
