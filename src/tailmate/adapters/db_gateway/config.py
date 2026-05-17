"""Gateway-specific runtime configuration."""

from __future__ import annotations

import os

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tailmate.bootstrap.config import AppEnvironment

DEFAULT_GATEWAY_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class GatewayConfig(BaseSettings):
    """Single source of truth for environment-derived gateway settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: AppEnvironment = Field(
        default=AppEnvironment.CLOUD,
        validation_alias=AliasChoices("TAILMATE_ENV"),
    )
    tailmate_project_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_PROJECT_ID"),
    )
    tailmate_location: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_LOCATION"),
    )
    firebase_project_id_override: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_FIREBASE_PROJECT_ID"),
    )
    agent_engine_resource_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_AGENT_ENGINE_RESOURCE_NAME"),
    )
    db_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DB_HOST"),
    )
    db_port: int = Field(
        default=5432,
        validation_alias=AliasChoices("DB_PORT"),
    )
    db_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DB_USER"),
    )
    db_password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("DB_PASSWORD"),
    )
    db_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DB_NAME"),
    )
    db_connect_timeout_seconds: int = Field(
        default=10,
        validation_alias=AliasChoices("DB_CONNECT_TIMEOUT_SECONDS"),
    )
    local_media_root: str = Field(
        default="/data/tailmate",
        validation_alias=AliasChoices("TAILMATE_LOCAL_MEDIA_ROOT"),
    )
    media_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_MEDIA_BUCKET"),
    )
    enable_public_query: bool = Field(
        default=False,
        validation_alias=AliasChoices("TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY"),
    )
    enable_internal_db: bool = Field(
        default=True,
        validation_alias=AliasChoices("TAILMATE_GATEWAY_ENABLE_INTERNAL_DB"),
    )
    enable_bridge_query: bool = Field(
        default=False,
        validation_alias=AliasChoices("TAILMATE_GATEWAY_ENABLE_BRIDGE_QUERY"),
    )
    public_query_rate_limit_requests: int = Field(
        default=30,
        validation_alias=AliasChoices("TAILMATE_PUBLIC_RATE_LIMIT_REQUESTS"),
    )
    public_query_rate_limit_window_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices("TAILMATE_PUBLIC_RATE_LIMIT_WINDOW_SECONDS"),
    )
    embedding_model: str = Field(
        default="text-embedding-004",
        validation_alias=AliasChoices("TAILMATE_EMBEDDING_MODEL"),
    )
    ffmpeg_binary: str = Field(
        default="ffmpeg",
        validation_alias=AliasChoices("FFMPEG_BINARY"),
    )
    audio_transcription_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("TAILMATE_AUDIO_TRANSCRIPTION_MODEL"),
    )
    gemini_timeout_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("TAILMATE_GEMINI_TIMEOUT_SECONDS"),
    )
    gateway_auth_audience: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TAILMATE_DB_GATEWAY_AUTH_AUDIENCE",
            "TAILMATE_DB_GATEWAY_AUDIENCE",
            "TAILMATE_DB_GATEWAY_URL",
        ),
    )
    gateway_allowed_callers: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DB_GATEWAY_ALLOWED_CALLERS"),
    )
    public_allowed_origins: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_PUBLIC_ALLOWED_ORIGINS"),
    )
    public_app_base_url: str = Field(
        default="https://tailmate-app.vercel.app",
        validation_alias=AliasChoices("TAILMATE_PUBLIC_APP_BASE_URL"),
    )
    gateway_require_auth: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DB_GATEWAY_REQUIRE_AUTH"),
    )
    max_upload_bytes: int = Field(
        default=DEFAULT_GATEWAY_MAX_UPLOAD_BYTES,
        validation_alias=AliasChoices("TAILMATE_DB_GATEWAY_MAX_UPLOAD_BYTES", "TAILMATE_MAX_UPLOAD_BYTES"),
    )

    @property
    def project_id(self) -> str:
        project_id = self.tailmate_project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError("TAILMATE_PROJECT_ID or GOOGLE_CLOUD_PROJECT is required.")
        return project_id

    @property
    def location(self) -> str:
        location = (
            self.tailmate_location
            or os.environ.get("GOOGLE_CLOUD_LOCATION")
            or os.environ.get("CLOUD_ML_REGION")
        )
        if not location:
            raise ValueError(
                "TAILMATE_LOCATION, GOOGLE_CLOUD_LOCATION, or CLOUD_ML_REGION is required."
            )
        return location

    @property
    def firebase_project_id(self) -> str:
        project_id = self.firebase_project_id_override or self.project_id
        if not project_id:
            raise ValueError(
                "TAILMATE_FIREBASE_PROJECT_ID, TAILMATE_PROJECT_ID, or GOOGLE_CLOUD_PROJECT is required."
            )
        return project_id

    @property
    def db_password_value(self) -> str:
        if self.db_password is None:
            raise ValueError("DB_PASSWORD is required.")
        password = self.db_password.get_secret_value()
        if not password:
            raise ValueError("DB_PASSWORD is required.")
        return password

    @property
    def auth_required(self) -> bool:
        if self.gateway_require_auth is not None:
            return self.gateway_require_auth
        return self.environment is not AppEnvironment.LOCAL

    @model_validator(mode="after")
    def validate_gateway_contract(self) -> "GatewayConfig":
        if self.db_port <= 0:
            raise ValueError("DB_PORT must be greater than zero.")
        if self.db_connect_timeout_seconds <= 0:
            raise ValueError("DB_CONNECT_TIMEOUT_SECONDS must be greater than zero.")
        if self.gemini_timeout_seconds <= 0:
            raise ValueError("TAILMATE_GEMINI_TIMEOUT_SECONDS must be greater than zero.")
        if self.max_upload_bytes <= 0:
            raise ValueError("TAILMATE_DB_GATEWAY_MAX_UPLOAD_BYTES must be greater than zero.")
        if self.public_query_rate_limit_requests <= 0:
            raise ValueError("TAILMATE_PUBLIC_RATE_LIMIT_REQUESTS must be greater than zero.")
        if self.public_query_rate_limit_window_seconds <= 0:
            raise ValueError("TAILMATE_PUBLIC_RATE_LIMIT_WINDOW_SECONDS must be greater than zero.")
        if not self.embedding_model.strip():
            raise ValueError("TAILMATE_EMBEDDING_MODEL must not be blank.")
        if not self.public_app_base_url.strip():
            raise ValueError("TAILMATE_PUBLIC_APP_BASE_URL must not be blank.")

        needs_database = (
            self.enable_internal_db or self.enable_public_query or self.enable_bridge_query
        )
        if needs_database:
            if not self.db_host:
                raise ValueError("DB_HOST is required.")
            if not self.db_user:
                raise ValueError("DB_USER is required.")
            _ = self.db_password_value
            if not self.db_name:
                raise ValueError("DB_NAME is required.")

        if self.enable_internal_db and self.environment is AppEnvironment.CLOUD and not self.media_bucket:
            raise ValueError("TAILMATE_MEDIA_BUCKET is required for gateway uploads in CLOUD mode.")

        if self.enable_public_query:
            _ = self.firebase_project_id

        if self.enable_public_query or self.enable_bridge_query:
            _ = self.project_id
            _ = self.location
            if not self.agent_engine_resource_name:
                raise ValueError("TAILMATE_AGENT_ENGINE_RESOURCE_NAME is required.")

        if self.enable_internal_db and self.auth_required:
            if not self.gateway_auth_audience:
                raise ValueError(
                    "TAILMATE_DB_GATEWAY_AUTH_AUDIENCE is required when gateway auth is enabled."
                )
            if not self.gateway_allowed_callers:
                raise ValueError(
                    "TAILMATE_DB_GATEWAY_ALLOWED_CALLERS is required when gateway auth is enabled."
                )

        return self

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        return cls()
