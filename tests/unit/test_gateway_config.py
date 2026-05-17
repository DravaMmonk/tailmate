from __future__ import annotations

import pytest

from tailmate.adapters.db_gateway.config import GatewayConfig
from tailmate.adapters.db_gateway.gateway_app import build_public_query_rate_limiter, create_app
from tailmate.adapters.db_gateway.rate_limiter import (
    DatabaseSlidingWindowRateLimiter,
    LocalFallbackSlidingWindowRateLimiter,
)


class FakeBlobStore:
    def put(self, logical_path: str, content_type: str, payload: bytes) -> str:
        del content_type, payload
        return logical_path

    def resolve_resource(self, logical_path: str) -> str:
        return logical_path

    def delete(self, logical_path: str) -> None:
        del logical_path


class FakeConnection:
    def cursor(self):
        raise AssertionError("Not used by this configuration test.")

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


class FakeDogProfileDBAdapter:
    def create_profile(self, request):
        del request
        raise AssertionError("Not used by this configuration test.")

    def load_profile(self, dog_id: str, *, requesting_user_id: str):
        del dog_id, requesting_user_id
        raise AssertionError("Not used by this configuration test.")

    def enrich_profile(self, request, extraction_result):
        del request, extraction_result
        raise AssertionError("Not used by this configuration test.")


def test_gateway_config_requires_database_host(set_env_values, monkeypatch) -> None:
    set_env_values(
        {
            "DB_HOST": None,
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_NAME": "tailmate",
            "TAILMATE_GATEWAY_ENABLE_INTERNAL_DB": "true",
            "TAILMATE_DB_GATEWAY_REQUIRE_AUTH": "false",
        }
    )

    with pytest.raises(ValueError, match="DB_HOST is required"):
        GatewayConfig(_env_file=None)


def test_gateway_config_resolves_google_cloud_fallbacks(set_env_values) -> None:
    set_env_values(
        {
            "GOOGLE_CLOUD_PROJECT": "google-project",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
            "DB_HOST": "127.0.0.1",
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_NAME": "tailmate",
            "TAILMATE_GATEWAY_ENABLE_INTERNAL_DB": "false",
            "TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY": "true",
            "TAILMATE_AGENT_ENGINE_RESOURCE_NAME": "projects/p/locations/l/reasoningEngines/r",
            "TAILMATE_PROJECT_ID": None,
            "TAILMATE_LOCATION": None,
        }
    )

    config = GatewayConfig(_env_file=None)

    assert config.project_id == "google-project"
    assert config.location == "us-central1"
    assert config.firebase_project_id == "google-project"


def test_gateway_config_prefers_tailmate_project_and_location_over_cloud_fallbacks(
    set_env_values,
) -> None:
    set_env_values(
        {
            "TAILMATE_PROJECT_ID": "tailmate-project",
            "TAILMATE_LOCATION": "us-central1",
            "GOOGLE_CLOUD_PROJECT": "google-project",
            "GOOGLE_CLOUD_LOCATION": "us-central1",
            "CLOUD_ML_REGION": "europe-west1",
            "DB_HOST": "127.0.0.1",
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_NAME": "tailmate",
            "TAILMATE_GATEWAY_ENABLE_INTERNAL_DB": "false",
            "TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY": "true",
            "TAILMATE_AGENT_ENGINE_RESOURCE_NAME": "projects/p/locations/l/reasoningEngines/r",
        }
    )

    config = GatewayConfig(_env_file=None)

    assert config.project_id == "tailmate-project"
    assert config.location == "us-central1"


def test_create_app_reads_internal_gateway_defaults_from_gateway_config(set_env_values) -> None:
    set_env_values(
        {
            "DB_HOST": "127.0.0.1",
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_NAME": "tailmate",
            "TAILMATE_GATEWAY_ENABLE_INTERNAL_DB": "true",
            "TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY": "false",
            "TAILMATE_DB_GATEWAY_REQUIRE_AUTH": "false",
            "TAILMATE_DB_GATEWAY_MAX_UPLOAD_BYTES": "2048",
            "FFMPEG_BINARY": "/usr/local/bin/ffmpeg",
        }
    )

    app = create_app(
        blob_store=FakeBlobStore(),
        db_connection_factory=lambda: FakeConnection(),
        dog_profile_db_adapter=FakeDogProfileDBAdapter(),
    )

    assert app.config["ENABLE_INTERNAL_DB"] is True
    assert app.config["AUTH_ENABLED"] is False
    assert app.config["MAX_CONTENT_LENGTH"] == 2048
    assert app.config["FFMPEG_BINARY"] == "/usr/local/bin/ffmpeg"


def test_build_public_query_rate_limiter_uses_local_fallback_in_local_mode(
    set_env_values,
) -> None:
    set_env_values(
        {
            "TAILMATE_ENV": "LOCAL",
            "DB_HOST": "127.0.0.1",
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_NAME": "tailmate",
            "TAILMATE_GATEWAY_ENABLE_INTERNAL_DB": "false",
            "TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY": "true",
            "TAILMATE_PROJECT_ID": "tailmate-project",
            "TAILMATE_LOCATION": "us-central1",
            "TAILMATE_AGENT_ENGINE_RESOURCE_NAME": "projects/p/locations/l/reasoningEngines/r",
        }
    )

    limiter = build_public_query_rate_limiter(GatewayConfig(_env_file=None))

    assert isinstance(limiter, LocalFallbackSlidingWindowRateLimiter)


def test_build_public_query_rate_limiter_keeps_database_mode_in_cloud(set_env_values) -> None:
    set_env_values(
        {
            "TAILMATE_ENV": "CLOUD",
            "DB_HOST": "127.0.0.1",
            "DB_USER": "postgres",
            "DB_PASSWORD": "secret",
            "DB_NAME": "tailmate",
            "TAILMATE_GATEWAY_ENABLE_INTERNAL_DB": "false",
            "TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY": "true",
            "TAILMATE_PROJECT_ID": "tailmate-project",
            "TAILMATE_LOCATION": "us-central1",
            "TAILMATE_AGENT_ENGINE_RESOURCE_NAME": "projects/p/locations/l/reasoningEngines/r",
        }
    )

    limiter = build_public_query_rate_limiter(GatewayConfig(_env_file=None))

    assert isinstance(limiter, DatabaseSlidingWindowRateLimiter)
