from __future__ import annotations

from io import BytesIO

from werkzeug.utils import secure_filename

from tailmate.contracts import types as contract_types
from tailmate.contracts.types import MAX_QUERY_MESSAGE_LENGTH
from tailmate.entrypoints.vertex_test_ui import VertexTestUiConfig, create_app


def build_app():
    app = create_app(
        config=VertexTestUiConfig(
            project_id="tailmate",
            location="us-central1",
            agent_resource_name="projects/1/locations/us-central1/reasoningEngines/123",
            default_user_id="user-default",
        )
    )
    app.config["TESTING"] = True
    return app


def test_from_env_loads_target_specific_runtime_settings(set_env_values) -> None:
    set_env_values(
        {
            "TAILMATE_PROJECT_ID": "tailmate-test",
            "TAILMATE_LOCATION": "us-central1",
            "TAILMATE_AGENT_ENGINE_RESOURCE_NAME": (
                "projects/1/locations/us-central1/reasoningEngines/test-engine"
            ),
            "TAILMATE_TEST_UI_TITLE": "Tailmate Test",
            "TAILMATE_TEST_UI_DEFAULT_DOG_ID": "dog-test",
            "TAILMATE_TEST_UI_USER_ID": "user-test",
            "TAILMATE_TEST_UI_DEFAULT_MESSAGE": "Check staged runtime",
            "TAILMATE_TEST_UI_MAX_UPLOAD_BYTES": 8 * 1024 * 1024,
            "K_SERVICE": "tailmate-vertex-test-ui-test",
        }
    )

    config = VertexTestUiConfig.from_env()

    assert config.project_id == "tailmate-test"
    assert config.location == "us-central1"
    assert config.agent_resource_name.endswith("/test-engine")
    assert config.page_title == "Tailmate Test"
    assert config.default_dog_id == "dog-test"
    assert config.default_user_id == "user-test"
    assert config.default_message == "Check staged runtime"
    assert config.max_upload_bytes == 8 * 1024 * 1024
    assert config.service_name == "tailmate-vertex-test-ui-test"


def test_healthz_reports_runtime_target() -> None:
    app = build_app()
    app.config["HEALTH_CHECK_HANDLER"] = lambda _config: (
        {"db_gateway": "ok", "gcs": "ok"},
        {},
    )
    client = app.test_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "ok",
        "checks": {"db_gateway": "ok", "gcs": "ok"},
        "project_id": "tailmate",
        "location": "us-central1",
        "agent_resource_name": "projects/1/locations/us-central1/reasoningEngines/123",
    }


def test_healthz_returns_503_when_any_deep_check_fails() -> None:
    app = build_app()
    app.config["HEALTH_CHECK_HANDLER"] = lambda _config: (
        {"db_gateway": "ok", "gcs": "error"},
        {"gcs": "bucket not writable"},
    )
    client = app.test_client()

    response = client.get("/healthz")

    assert response.status_code == 503
    assert response.get_json() == {
        "status": "error",
        "checks": {"db_gateway": "ok", "gcs": "error"},
        "errors": {"gcs": "bucket not writable"},
        "project_id": "tailmate",
        "location": "us-central1",
        "agent_resource_name": "projects/1/locations/us-central1/reasoningEngines/123",
    }


def test_api_query_sends_text_payload() -> None:
    app = build_app()
    captured: dict[str, object] = {}

    def fake_query(_config, payload):
        captured["payload"] = payload
        return {
            "session_id": payload["session_id"],
            "response": "Created a dog profile for Peanut.",
            "metadata": {"dog_id": "dog-1"},
            "error": None,
        }

    app.config["QUERY_AGENT_HANDLER"] = fake_query
    client = app.test_client()

    response = client.post(
        "/api/query",
        data={
            "session_id": "session-1",
            "dog_id": "dog-1",
            "user_id": "user-1",
            "message": "My dog is named Peanut.",
        },
    )

    assert response.status_code == 200
    assert captured["payload"] == {
        "session_id": "session-1",
        "message": "My dog is named Peanut.",
        "metadata": {"dog_id": "dog-1", "user_id": "user-1"},
    }
    assert response.get_json()["response"]["response"] == "Created a dog profile for Peanut."


def test_api_query_builds_strip_metadata_request_for_uploads() -> None:
    app = build_app()
    captured: dict[str, object] = {}

    def fake_query(_config, payload):
        captured["payload"] = payload
        return {
            "session_id": payload["session_id"],
            "response": "Sanitized media stored at gs://tailmate/sanitized.jpg.",
            "metadata": {"strip_metadata": {"resource_uri": "gs://tailmate/sanitized.jpg"}},
            "error": None,
        }

    app.config["QUERY_AGENT_HANDLER"] = fake_query
    client = app.test_client()

    response = client.post(
        "/api/query",
        data={
            "session_id": "session-2",
            "dog_id": "dog-2",
            "message": "",
            "resource_kind": "auto",
            "file": (BytesIO(b"binary-image"), "../../evil photo.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    payload = captured["payload"]
    assert payload["message"] == "Please sanitize and store this upload."
    assert payload["metadata"]["dog_id"] == "dog-2"
    assert "user_id" not in payload["metadata"]
    assert payload["metadata"]["strip_metadata_request"]["resource_kind"] == "images"
    assert payload["metadata"]["strip_metadata_request"]["filename"] == secure_filename(
        "../../evil photo.jpg"
    )
    assert response.get_json()["upload"]["filename"] == secure_filename(
        "../../evil photo.jpg"
    )
    assert response.get_json()["request_preview"]["metadata"]["strip_metadata_request"][
        "payload_base64"
    ] == "<redacted>"


def test_api_query_infers_audio_resource_kind_for_audio_uploads() -> None:
    app = build_app()
    captured: dict[str, object] = {}

    def fake_query(_config, payload):
        captured["payload"] = payload
        return {
            "session_id": payload["session_id"],
            "response": "Transcribed audio.",
            "metadata": {"strip_metadata": {"resource_uri": "gs://tailmate/voice.m4a"}},
            "error": None,
        }

    app.config["QUERY_AGENT_HANDLER"] = fake_query
    client = app.test_client()

    response = client.post(
        "/api/query",
        data={
            "session_id": "session-audio",
            "dog_id": "dog-audio",
            "message": "",
            "resource_kind": "auto",
            "file": (BytesIO(b"binary-audio"), "voice.m4a", "audio/mp4"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert captured["payload"]["metadata"]["strip_metadata_request"]["resource_kind"] == "audio"


def test_api_query_rejects_overlong_messages() -> None:
    app = build_app()
    client = app.test_client()

    response = client.post(
        "/api/query",
        data={
            "session_id": "session-4",
            "message": "x" * (MAX_QUERY_MESSAGE_LENGTH + 1),
        },
    )

    assert response.status_code == 400
    assert "at most 4000 characters" in response.get_json()["error"]


def test_api_query_rejects_image_uploads_over_kind_limit_with_413(monkeypatch) -> None:
    monkeypatch.setattr(contract_types, "DEFAULT_IMAGE_UPLOAD_BYTES", 64)
    app = build_app()
    client = app.test_client()

    response = client.post(
        "/api/query",
        data={
            "session_id": "session-5",
            "message": "",
            "resource_kind": "images",
            "file": (BytesIO(b"x" * 65), "photo.jpg", "image/jpeg"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 413
    assert "Current limit: 52428800 bytes." in response.get_json()["error"]


def test_api_query_omits_blank_user_id() -> None:
    app = build_app()
    captured: dict[str, object] = {}

    def fake_query(_config, payload):
        captured["payload"] = payload
        return {
            "session_id": payload["session_id"],
            "response": "ok",
            "metadata": {},
            "error": None,
        }

    app.config["QUERY_AGENT_HANDLER"] = fake_query
    client = app.test_client()

    response = client.post(
        "/api/query",
        data={
            "session_id": "session-3",
            "dog_id": "dog-3",
            "user_id": "   ",
            "message": "health check",
        },
    )

    assert response.status_code == 200
    assert captured["payload"] == {
        "session_id": "session-3",
        "message": "health check",
        "metadata": {"dog_id": "dog-3"},
    }
