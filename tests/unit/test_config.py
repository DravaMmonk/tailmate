from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr

from tailmate.bootstrap.config import (
    AppConfig,
    AppEnvironment,
    ExtractionStrategy,
    IntentClassifierStrategy,
)

def test_local_mode_allows_missing_cloud_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=LOCAL",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_DB_NAME=postgres",
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env()

    assert config.environment is AppEnvironment.LOCAL
    assert config.db_user == "user"
    assert config.db_name == "postgres"
    assert isinstance(config.db_password, SecretStr)
    assert "SecretStr('**********')" in repr(config)
    assert "SecretStr('pass')" not in repr(config)
    assert config.media_bucket is None
    assert config.network_attachment is None
    assert config.extraction_strategy is ExtractionStrategy.COMPOSITE
    assert config.intent_classifier_strategy is IntentClassifierStrategy.HYBRID


def test_local_mode_warns_on_placeholder_database_password(
    tmp_path,
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=LOCAL",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=change-me",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_DB_NAME=postgres",
            ]
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        config = AppConfig.from_env()

    assert config.environment is AppEnvironment.LOCAL
    assert config.db_password is not None
    assert config.db_password.get_secret_value() == "change-me"
    assert any(
        "placeholder value 'change-me'" in record.getMessage() for record in caplog.records
    )


def test_intent_classifier_threshold_must_be_in_range(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=LOCAL",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_INTENT_LLM_CONFIDENCE_THRESHOLD=1.5",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="TAILMATE_INTENT_LLM_CONFIDENCE_THRESHOLD"):
        AppConfig.from_env()


def test_cloud_mode_requires_cloud_specific_settings(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="TAILMATE_NETWORK_ATTACHMENT"):
        AppConfig.from_env()


def test_cloud_mode_allows_gateway_without_direct_database_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
                "TAILMATE_DB_GATEWAY_URL=https://tailmate-db-gateway-abc.a.run.app",
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env()

    assert config.uses_db_gateway is True
    assert config.requires_direct_database is False
    assert config.db_gateway_url == "https://tailmate-db-gateway-abc.a.run.app"
    assert config.db_user is None
    assert config.db_password is None
    assert config.db_ip is None


def test_cloud_mode_requires_https_gateway_url(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
                "TAILMATE_DB_GATEWAY_URL=http://internal-gateway",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="TAILMATE_DB_GATEWAY_URL"):
        AppConfig.from_env()


def test_flash_extraction_strategy_allows_vertex_ai_adc_without_gemini_api_key(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=LOCAL",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_EXTRACTION_STRATEGY=flash",
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env()

    assert config.extraction_strategy is ExtractionStrategy.FLASH
    assert config.gemini_api_key is None
    assert config.gemini_location == "global"
    assert config.gemini_flash_model == "gemini-2.5-flash"


def test_cloud_mode_rejects_placeholder_database_password(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=change-me",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
                "TAILMATE_NETWORK_ATTACHMENT=projects/test/regions/us-central1/networkAttachments/tailmate",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="placeholder value 'change-me'"):
        AppConfig.from_env()


def test_cloud_mode_rejects_malformed_network_attachment(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_MEDIA_BUCKET=tailmate-local-bucket",
                "TAILMATE_NETWORK_ATTACHMENT=tailmate-attachment",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="TAILMATE_NETWORK_ATTACHMENT"):
        AppConfig.from_env()


def test_cloud_mode_rejects_public_database_ip(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=8.8.8.8",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
                "TAILMATE_NETWORK_ATTACHMENT=projects/test/regions/us-central1/networkAttachments/tailmate",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="private IP address"):
        AppConfig.from_env()


def test_cloud_mode_rejects_non_positive_database_timeout(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_DB_CONNECT_TIMEOUT_SECONDS=0",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
                "TAILMATE_NETWORK_ATTACHMENT=projects/test/regions/us-central1/networkAttachments/tailmate",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="TAILMATE_DB_CONNECT_TIMEOUT_SECONDS"):
        AppConfig.from_env()


def test_secret_manager_reference_is_resolved(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=projects/test/secrets/tailmate-db-password/versions/latest",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
                "TAILMATE_NETWORK_ATTACHMENT=projects/test/regions/us-central1/networkAttachments/tailmate",
            ]
        ),
        encoding="utf-8",
    )

    config = AppConfig.from_env()

    assert isinstance(config.db_password, SecretStr)
    assert config.db_password.get_secret_value() == (
        "projects/test/secrets/tailmate-db-password/versions/latest"
    )


def test_cloud_mode_requires_complete_dns_peering_config(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=CLOUD",
                "TAILMATE_DB_USER=user",
                "TAILMATE_DB_PASSWORD=pass",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_MEDIA_BUCKET=tailmate-bucket",
                "TAILMATE_NETWORK_ATTACHMENT=projects/test/regions/us-central1/networkAttachments/tailmate",
                "TAILMATE_DNS_PEERING_DOMAIN=tailmate.internal.",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="TAILMATE_DNS_PEERING_DOMAIN"):
        AppConfig.from_env()


def test_skill_feature_flags_are_normalized() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_ENV="LOCAL",
        TAILMATE_DB_USER="user",
        TAILMATE_DB_PASSWORD="pass",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_ENABLED_SKILLS=" strip_metadata,foo_bar ",
        TAILMATE_DISABLED_SKILLS=" foo_bar , baz ",
    )

    assert config.enabled_skill_ids == {"strip_metadata", "foo_bar"}
    assert config.disabled_skill_ids == {"foo_bar", "baz"}


def test_knowledge_base_settings_default_to_disabled() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_ENV="LOCAL",
        TAILMATE_DB_USER="user",
        TAILMATE_DB_PASSWORD="pass",
        TAILMATE_DB_IP="10.0.0.10",
    )

    assert config.kb_enabled is False
    assert config.embedding_model == "text-embedding-004"
    assert config.kb_threshold == 0.75


def test_knowledge_base_threshold_must_be_between_zero_and_one() -> None:
    with pytest.raises(ValueError, match="TAILMATE_KB_THRESHOLD"):
        AppConfig(
            _env_file=None,
            TAILMATE_PROJECT_ID="test-project",
            TAILMATE_LOCATION="us-central1",
            TAILMATE_ENV="LOCAL",
            TAILMATE_DB_USER="user",
            TAILMATE_DB_PASSWORD="pass",
            TAILMATE_DB_IP="10.0.0.10",
            TAILMATE_KB_THRESHOLD=1.1,
        )


def test_knowledge_base_embedding_model_must_not_be_blank() -> None:
    with pytest.raises(ValueError, match="TAILMATE_EMBEDDING_MODEL"):
        AppConfig(
            _env_file=None,
            TAILMATE_PROJECT_ID="test-project",
            TAILMATE_LOCATION="us-central1",
            TAILMATE_ENV="LOCAL",
            TAILMATE_DB_USER="user",
            TAILMATE_DB_PASSWORD="pass",
            TAILMATE_DB_IP="10.0.0.10",
            TAILMATE_EMBEDDING_MODEL="   ",
        )
