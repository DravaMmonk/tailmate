from __future__ import annotations

from pathlib import Path

from google.auth.exceptions import DefaultCredentialsError
import pytest

from tailmate.contracts.constants import DOG_PROFILE_SKILL_ID, STRIP_METADATA_SKILL_ID
from tailmate.adapters.db_gateway.conversation_store import GatewayConversationStore
from tailmate.adapters.db_gateway.media_store import GatewaySanitizedMediaStore
from tailmate.adapters.dog_profile.extractors import LLMFlashExtractor
from tailmate.adapters.gcs.gcs_adapter import GcsBlobStore
from tailmate.adapters.knowledge_base import GatewayKnowledgeRetriever, PgVectorKnowledgeRetriever
from tailmate.adapters.localfs.blob_store import LocalBlobStore
from tailmate.adapters.media.sanitized_media_store import DirectSanitizedMediaStore
from tailmate.agent_runtime.services.hybrid_intent_classifier import HybridIntentClassifier
from tailmate.agent_runtime.services.rule_based_intent_classifier import RuleBasedIntentClassifier
from tailmate.bootstrap.config import AppConfig, IntentClassifierStrategy
from tailmate.bootstrap.container import AppContainer
from tailmate.contracts.errors import ConfigurationError


def test_container_uses_hybrid_intent_classifier_by_default() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
    )

    classifier = AppContainer(config=config).build_intent_classifier()

    assert isinstance(classifier, HybridIntentClassifier)


def test_container_honors_rule_intent_classifier_strategy() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_INTENT_CLASSIFIER=IntentClassifierStrategy.RULE,
    )

    classifier = AppContainer(config=config).build_intent_classifier()

    assert isinstance(classifier, RuleBasedIntentClassifier)


def test_container_uses_local_blob_store_for_local_mode() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_LOCAL_MEDIA_ROOT="/data/tailmate-test",
    )

    blob_store = AppContainer(config=config).build_blob_store()

    assert isinstance(blob_store, LocalBlobStore)
    assert str(blob_store.root_dir) == "/data/tailmate-test"


def test_container_builds_local_database_url_from_atomic_fields() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_LOCAL_TUNNEL_HOST="127.0.0.1",
        TAILMATE_LOCAL_TUNNEL_PORT=15432,
    )

    database_url = AppContainer(config=config).build_database_url()

    assert database_url == "postgresql+psycopg2://postgres:pw@127.0.0.1:15432/postgres"

    connect_args = AppContainer(config=config).build_database_connect_args()

    assert connect_args == {
        "connect_timeout": 10,
        "application_name": "tailmate_root",
    }


def test_container_uses_gcs_blob_store_for_cloud_mode() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_NETWORK_ATTACHMENT="projects/test/regions/us-central1/networkAttachments/tailmate",
    )

    blob_store = AppContainer(config=config).build_blob_store()

    assert isinstance(blob_store, GcsBlobStore)
    assert blob_store.bucket_name == "tailmate-bucket"
    assert blob_store.project_id == "test-project"
    assert blob_store.api_endpoint is None


def test_container_uses_gateway_session_store_for_cloud_gateway_mode() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_DB_GATEWAY_URL="https://tailmate-db-gateway-abc.a.run.app",
    )

    session_store = AppContainer(config=config).build_session_store()

    assert isinstance(session_store, GatewayConversationStore)


def test_container_registers_strip_metadata_skill_for_local_mode() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
    )
    container = AppContainer(config=config)

    media_store = container.build_sanitized_media_store()
    registry = container.build_skill_registry()

    assert isinstance(media_store, DirectSanitizedMediaStore)
    assert [skill.spec.skill_id for skill in registry.all()] == [
        DOG_PROFILE_SKILL_ID,
        STRIP_METADATA_SKILL_ID,
    ]


def test_container_registers_strip_metadata_skill_for_cloud_gateway_mode() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_DB_GATEWAY_URL="https://tailmate-db-gateway-abc.a.run.app",
    )
    container = AppContainer(config=config)

    media_store = container.build_sanitized_media_store()
    registry = container.build_skill_registry()

    assert isinstance(media_store, GatewaySanitizedMediaStore)
    assert [skill.spec.skill_id for skill in registry.all()] == [
        DOG_PROFILE_SKILL_ID,
        STRIP_METADATA_SKILL_ID,
    ]


def test_container_fails_fast_for_cloud_direct_mode_with_strip_metadata_enabled() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_NETWORK_ATTACHMENT="projects/test/regions/us-central1/networkAttachments/tailmate",
    )

    with pytest.raises(ConfigurationError, match="disable strip_metadata via TAILMATE_DISABLED_SKILLS"):
        AppContainer(config=config).build_orchestrator()


def test_container_allows_cloud_direct_mode_when_strip_metadata_is_disabled() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_NETWORK_ATTACHMENT="projects/test/regions/us-central1/networkAttachments/tailmate",
        TAILMATE_DISABLED_SKILLS=STRIP_METADATA_SKILL_ID,
    )

    registry = AppContainer(config=config).build_skill_registry()

    assert [skill.spec.skill_id for skill in registry.all()] == [DOG_PROFILE_SKILL_ID]


def test_container_builds_cloud_database_url_from_atomic_fields() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_NETWORK_ATTACHMENT="projects/test/regions/us-central1/networkAttachments/tailmate",
    )

    database_url = AppContainer(config=config).build_database_url()

    assert database_url == "postgresql+psycopg2://postgres:pw@10.0.0.10:5432/postgres"

    connect_args = AppContainer(config=config).build_database_connect_args()

    assert connect_args == {
        "connect_timeout": 10,
        "application_name": "tailmate_root",
    }


def test_container_rejects_direct_database_url_when_gateway_mode_is_enabled() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_DB_GATEWAY_URL="https://tailmate-db-gateway-abc.a.run.app",
    )

    with pytest.raises(ConfigurationError, match="direct database URLs are disabled"):
        AppContainer(config=config).build_database_url()


def test_container_resolves_secret_manager_password(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="projects/test/secrets/tailmate-db-password/versions/latest",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_NETWORK_ATTACHMENT="projects/test/regions/us-central1/networkAttachments/tailmate",
    )
    container = AppContainer(config=config)

    class FakePayload:
        data = b"resolved-password"

    class FakeResponse:
        payload = FakePayload()

    class FakeSecretClient:
        def access_secret_version(self, request):
            assert request == {
                "name": "projects/test/secrets/tailmate-db-password/versions/latest"
            }
            return FakeResponse()

    monkeypatch.setattr(container, "_build_secret_client", lambda: FakeSecretClient())

    assert container.build_database_url() == (
        "postgresql+psycopg2://postgres:resolved-password@10.0.0.10:5432/postgres"
    )
    assert container.build_database_connect_args() == {
        "connect_timeout": 10,
        "application_name": "tailmate_root",
    }


def test_container_resolves_secret_manager_gemini_api_key(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_EXTRACTION_STRATEGY="flash",
        TAILMATE_GEMINI_API_KEY="projects/test/secrets/tailmate-gemini/versions/latest",
        TAILMATE_GEMINI_FLASH_MODEL="gemini-2.0-flash",
    )
    container = AppContainer(config=config)

    class FakePayload:
        data = b"resolved-gemini-key"

    class FakeResponse:
        payload = FakePayload()

    class FakeSecretClient:
        def access_secret_version(self, request):
            assert request == {"name": "projects/test/secrets/tailmate-gemini/versions/latest"}
            return FakeResponse()

    monkeypatch.setattr(container, "_build_secret_client", lambda: FakeSecretClient())

    extractor = container.build_profile_extractor()

    assert isinstance(extractor, LLMFlashExtractor)
    assert extractor.client.api_key == "resolved-gemini-key"


def test_container_builds_flash_extractor_from_vertex_ai_adc(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_EXTRACTION_STRATEGY="flash",
    )
    container = AppContainer(config=config)
    fake_credentials = object()

    monkeypatch.setattr(
        "tailmate.bootstrap.container.google.auth.default",
        lambda scopes: (fake_credentials, "test-project"),
    )

    extractor = container.build_profile_extractor()

    assert isinstance(extractor, LLMFlashExtractor)
    assert extractor.client.api_key is None
    assert extractor.client.credentials is fake_credentials
    assert extractor.client.project_id == "test-project"
    assert extractor.client.location == "global"


def test_container_honors_explicit_gemini_location_override(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_GEMINI_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_EXTRACTION_STRATEGY="flash",
    )
    container = AppContainer(config=config)
    fake_credentials = object()

    monkeypatch.setattr(
        "tailmate.bootstrap.container.google.auth.default",
        lambda scopes: (fake_credentials, "test-project"),
    )

    extractor = container.build_profile_extractor()

    assert isinstance(extractor, LLMFlashExtractor)
    assert extractor.client.location == "us-central1"


def test_container_rejects_flash_extractor_when_no_adc_or_api_key(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_EXTRACTION_STRATEGY="flash",
    )
    container = AppContainer(config=config)

    def raise_missing_credentials(*, scopes):
        raise DefaultCredentialsError("missing adc")

    monkeypatch.setattr(
        "tailmate.bootstrap.container.google.auth.default",
        raise_missing_credentials,
    )

    with pytest.raises(ConfigurationError, match="Vertex AI ADC or TAILMATE_GEMINI_API_KEY"):
        container.build_profile_extractor()


def test_container_disables_knowledge_retriever_by_default() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
    )

    retriever = AppContainer(config=config).build_knowledge_retriever()

    assert retriever is None


def test_container_builds_direct_knowledge_retriever_for_local_mode(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_KB_ENABLED=True,
    )
    container = AppContainer(config=config)
    fake_credentials = object()

    monkeypatch.setattr(container, "_get_vertex_ai_credentials", lambda: fake_credentials)

    retriever = container.build_knowledge_retriever()

    assert isinstance(retriever, PgVectorKnowledgeRetriever)
    assert retriever.embedding_client.credentials is fake_credentials


def test_container_honors_explicit_gemini_location_override_for_knowledge_answers(
    monkeypatch,
) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="LOCAL",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_GEMINI_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_KB_ENABLED=True,
    )
    container = AppContainer(config=config)
    fake_credentials = object()

    monkeypatch.setattr(container, "_get_vertex_ai_credentials", lambda: fake_credentials)

    retriever = container.build_knowledge_retriever()

    assert isinstance(retriever, PgVectorKnowledgeRetriever)
    assert retriever.answer_client.location == "us-central1"


def test_container_builds_direct_knowledge_retriever_for_cloud_direct_mode(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_NETWORK_ATTACHMENT="projects/test/regions/us-central1/networkAttachments/tailmate",
        TAILMATE_KB_ENABLED=True,
    )
    container = AppContainer(config=config)
    fake_credentials = object()

    monkeypatch.setattr(container, "_get_vertex_ai_credentials", lambda: fake_credentials)

    retriever = container.build_knowledge_retriever()

    assert isinstance(retriever, PgVectorKnowledgeRetriever)
    assert retriever.answer_client.credentials is fake_credentials


def test_container_builds_gateway_knowledge_retriever_for_cloud_gateway_mode(monkeypatch) -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_DB_GATEWAY_URL="https://tailmate-db-gateway-abc.a.run.app",
        TAILMATE_KB_ENABLED=True,
    )
    container = AppContainer(config=config)
    fake_credentials = object()

    monkeypatch.setattr(container, "_get_vertex_ai_credentials", lambda: fake_credentials)

    retriever = container.build_knowledge_retriever()

    assert isinstance(retriever, GatewayKnowledgeRetriever)


def test_container_includes_configured_db_sslmode() -> None:
    config = AppConfig(
        _env_file=None,
        TAILMATE_ENV="CLOUD",
        TAILMATE_PROJECT_ID="test-project",
        TAILMATE_LOCATION="us-central1",
        TAILMATE_DB_USER="postgres",
        TAILMATE_DB_PASSWORD="pw",
        TAILMATE_DB_IP="10.0.0.10",
        TAILMATE_DB_NAME="postgres",
        TAILMATE_DB_SSLMODE="disable",
        TAILMATE_MEDIA_BUCKET="tailmate-bucket",
        TAILMATE_NETWORK_ATTACHMENT="projects/test/regions/us-central1/networkAttachments/tailmate",
    )

    connect_args = AppContainer(config=config).build_database_connect_args()

    assert connect_args == {
        "connect_timeout": 10,
        "application_name": "tailmate_root",
        "sslmode": "disable",
    }


def test_alembic_env_builds_database_url_from_container(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=LOCAL",
                "TAILMATE_DB_USER=postgres",
                "TAILMATE_DB_PASSWORD=pw",
                "TAILMATE_DB_IP=10.0.0.10",
                "TAILMATE_DB_NAME=postgres",
                "TAILMATE_LOCAL_TUNNEL_HOST=127.0.0.1",
                "TAILMATE_LOCAL_TUNNEL_PORT=15432",
            ]
        ),
        encoding="utf-8",
    )

    from tailmate.adapters.database.migrations.env import build_runtime_database_url

    assert build_runtime_database_url() == (
        "postgresql+psycopg2://postgres:pw@127.0.0.1:15432/postgres"
    )


def test_alembic_env_honors_explicit_database_url_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAILMATE_PROJECT_ID=test-project",
                "TAILMATE_LOCATION=us-central1",
                "TAILMATE_ENV=LOCAL",
                "TAILMATE_DB_USER=postgres",
                "TAILMATE_DB_PASSWORD=pw",
                "TAILMATE_DB_IP=10.0.0.10",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TAILMATE_ALEMBIC_DATABASE_URL", "sqlite:///override.sqlite")

    from tailmate.adapters.database.migrations.env import build_runtime_database_url

    assert build_runtime_database_url() == "sqlite:///override.sqlite"
