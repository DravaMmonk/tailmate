"""Canonical runtime configuration for the Tailmate application."""

from __future__ import annotations

from enum import StrEnum
from ipaddress import ip_address
import logging
import os

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnvironment(StrEnum):
    """Runtime modes supported by the application."""

    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class ExtractionStrategy(StrEnum):
    """Available dog profile extraction strategies."""

    RULE = "rule"
    FLASH = "flash"
    PRO = "pro"
    COMPOSITE = "composite"


class IntentClassifierStrategy(StrEnum):
    """Available intent classification strategies."""

    RULE = "rule"
    HYBRID = "hybrid"
    LLM = "llm"


logger = logging.getLogger(__name__)
DEFAULT_DB_PASSWORD_PLACEHOLDER = "change-me"  # nosec B105


class AppConfig(BaseSettings):
    """Single source of truth for environment-derived configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: AppEnvironment = Field(
        default=AppEnvironment.LOCAL,
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
    agent_name: str = Field(
        default="tailmate_root",
        validation_alias=AliasChoices("TAILMATE_AGENT_NAME"),
    )
    service_account: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_SERVICE_ACCOUNT", "SERVICE_ACCOUNT"),
    )
    db_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DB_USER"),
    )
    db_password: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DB_PASSWORD"),
    )
    db_ip: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DB_IP"),
    )
    db_name: str = Field(
        default="tailmate",
        validation_alias=AliasChoices("TAILMATE_DB_NAME"),
    )
    db_connect_timeout_seconds: int = Field(
        default=10,
        validation_alias=AliasChoices("TAILMATE_DB_CONNECT_TIMEOUT_SECONDS"),
    )
    db_sslmode: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DB_SSLMODE"),
    )
    db_gateway_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DB_GATEWAY_URL"),
    )
    db_gateway_timeout_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices("TAILMATE_DB_GATEWAY_TIMEOUT_SECONDS"),
    )
    network_attachment: str | None = Field(
        default=None,
        pattern=r"^projects/[^/]+/regions/[^/]+/networkAttachments/[^/]+$",
        validation_alias=AliasChoices("TAILMATE_NETWORK_ATTACHMENT"),
    )
    dns_peering_domain: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DNS_PEERING_DOMAIN"),
    )
    dns_peering_target_project: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DNS_PEERING_TARGET_PROJECT"),
    )
    dns_peering_target_network: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DNS_PEERING_TARGET_NETWORK"),
    )
    outbound_proxy_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_OUTBOUND_PROXY_URL"),
    )
    no_proxy: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_NO_PROXY"),
    )
    media_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_MEDIA_BUCKET"),
    )
    local_media_root: str = Field(
        default="/data/tailmate",
        validation_alias=AliasChoices("TAILMATE_LOCAL_MEDIA_ROOT"),
    )
    local_tunnel_host: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("TAILMATE_LOCAL_TUNNEL_HOST"),
    )
    local_tunnel_port: int = Field(
        default=5432,
        validation_alias=AliasChoices("TAILMATE_LOCAL_TUNNEL_PORT"),
    )
    enabled_skills_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_ENABLED_SKILLS"),
    )
    disabled_skills_raw: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_DISABLED_SKILLS"),
    )
    extraction_strategy: ExtractionStrategy = Field(
        default=ExtractionStrategy.COMPOSITE,
        validation_alias=AliasChoices("TAILMATE_EXTRACTION_STRATEGY"),
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("TAILMATE_GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    gemini_location: str = Field(
        default="global",
        validation_alias=AliasChoices("TAILMATE_GEMINI_LOCATION"),
    )
    gemini_flash_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("TAILMATE_GEMINI_FLASH_MODEL"),
    )
    audio_transcription_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("TAILMATE_AUDIO_TRANSCRIPTION_MODEL"),
    )
    gemini_pro_model: str = Field(
        default="gemini-2.5-pro",
        validation_alias=AliasChoices("TAILMATE_GEMINI_PRO_MODEL"),
    )
    gemini_timeout_seconds: int = Field(
        default=15,
        validation_alias=AliasChoices("TAILMATE_GEMINI_TIMEOUT_SECONDS"),
    )
    kb_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("TAILMATE_KB_ENABLED"),
    )
    embedding_model: str = Field(
        default="text-embedding-004",
        validation_alias=AliasChoices("TAILMATE_EMBEDDING_MODEL"),
    )
    kb_threshold: float = Field(
        default=0.75,
        validation_alias=AliasChoices("TAILMATE_KB_THRESHOLD"),
    )
    intent_classifier_strategy: IntentClassifierStrategy = Field(
        default=IntentClassifierStrategy.HYBRID,
        validation_alias=AliasChoices("TAILMATE_INTENT_CLASSIFIER"),
    )
    intent_llm_confidence_threshold: float = Field(
        default=0.7,
        validation_alias=AliasChoices("TAILMATE_INTENT_LLM_CONFIDENCE_THRESHOLD"),
    )

    @property
    def project_id(self) -> str:
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or self.tailmate_project_id
        if not project_id:
            raise ValueError("TAILMATE_PROJECT_ID is required.")
        return project_id

    @property
    def location(self) -> str:
        location = (
            os.environ.get("GOOGLE_CLOUD_LOCATION")
            or os.environ.get("CLOUD_ML_REGION")
            or self.tailmate_location
        )
        if not location:
            raise ValueError("TAILMATE_LOCATION is required.")
        return location

    @property
    def uses_db_gateway(self) -> bool:
        return self.environment is AppEnvironment.CLOUD and bool(self.db_gateway_url)

    @property
    def requires_direct_database(self) -> bool:
        return not self.uses_db_gateway

    @property
    def enabled_skill_ids(self) -> set[str]:
        return _parse_skill_flag_list(self.enabled_skills_raw)

    @property
    def disabled_skill_ids(self) -> set[str]:
        return _parse_skill_flag_list(self.disabled_skills_raw)

    @model_validator(mode="after")
    def validate_runtime_contract(self) -> "AppConfig":
        _ = self.project_id
        _ = self.location
        if self.db_gateway_timeout_seconds <= 0:
            raise ValueError("TAILMATE_DB_GATEWAY_TIMEOUT_SECONDS must be greater than zero.")
        if self.gemini_timeout_seconds <= 0:
            raise ValueError("TAILMATE_GEMINI_TIMEOUT_SECONDS must be greater than zero.")
        if not self.audio_transcription_model.strip():
            raise ValueError("TAILMATE_AUDIO_TRANSCRIPTION_MODEL is required.")
        if not self.embedding_model.strip():
            raise ValueError("TAILMATE_EMBEDDING_MODEL is required.")
        if not 0.0 <= self.kb_threshold <= 1.0:
            raise ValueError("TAILMATE_KB_THRESHOLD must be between 0.0 and 1.0.")
        if not 0.0 <= self.intent_llm_confidence_threshold <= 1.0:
            raise ValueError(
                "TAILMATE_INTENT_LLM_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0."
            )
        if self.uses_db_gateway and self.db_gateway_url is not None:
            if not self.db_gateway_url.startswith("https://"):
                raise ValueError("TAILMATE_DB_GATEWAY_URL must be an HTTPS URL.")
        if self.db_password is not None:
            db_password = self.db_password.get_secret_value()
            if not db_password:
                raise ValueError("TAILMATE_DB_PASSWORD is required.")
            if db_password == DEFAULT_DB_PASSWORD_PLACEHOLDER:
                placeholder_message = (
                    "TAILMATE_DB_PASSWORD still uses the placeholder value 'change-me'. "
                    "Set the real database password before deploying to CLOUD."
                )
                if self.environment is AppEnvironment.CLOUD:
                    raise ValueError(placeholder_message)
                logger.warning(placeholder_message)
        if self.requires_direct_database:
            if not self.db_user:
                raise ValueError("TAILMATE_DB_USER is required.")
            if self.db_password is None:
                raise ValueError("TAILMATE_DB_PASSWORD is required.")
            if not self.db_ip:
                raise ValueError("TAILMATE_DB_IP is required.")
            if self.db_connect_timeout_seconds <= 0:
                raise ValueError("TAILMATE_DB_CONNECT_TIMEOUT_SECONDS must be greater than zero.")
        if self.db_sslmode is not None:
            allowed_sslmodes = {
                "disable",
                "allow",
                "prefer",
                "require",
                "verify-ca",
                "verify-full",
            }
            if self.db_sslmode not in allowed_sslmodes:
                raise ValueError(
                    "TAILMATE_DB_SSLMODE must be one of: "
                    "disable, allow, prefer, require, verify-ca, verify-full."
                )

        if self.environment is AppEnvironment.CLOUD:
            if not self.media_bucket:
                raise ValueError("TAILMATE_MEDIA_BUCKET is required when TAILMATE_ENV=CLOUD.")
            if not self.uses_db_gateway:
                if not self.network_attachment:
                    raise ValueError(
                        "TAILMATE_NETWORK_ATTACHMENT is required when TAILMATE_ENV=CLOUD "
                        "and TAILMATE_DB_GATEWAY_URL is not set."
                    )
                dns_peering_values = (
                    self.dns_peering_domain,
                    self.dns_peering_target_project,
                    self.dns_peering_target_network,
                )
                if any(dns_peering_values) and not all(dns_peering_values):
                    raise ValueError(
                        "TAILMATE_DNS_PEERING_DOMAIN, TAILMATE_DNS_PEERING_TARGET_PROJECT, and "
                        "TAILMATE_DNS_PEERING_TARGET_NETWORK must all be set together."
                    )
                if self.db_ip is None or not ip_address(self.db_ip).is_private:
                    raise ValueError(
                        "TAILMATE_DB_IP must be a private IP address when TAILMATE_ENV=CLOUD "
                        "without TAILMATE_DB_GATEWAY_URL."
                    )
            return self

        return self

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls()


def _parse_skill_flag_list(raw_value: str | None) -> set[str]:
    """Parse a comma-delimited skill flag list into normalized ids."""

    if raw_value is None:
        return set()
    return {
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    }
