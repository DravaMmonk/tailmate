"""Dependency assembly root for the Tailmate application."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import cast

import google.auth
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import secretmanager

from tailmate.adapters.db_gateway.client import DbGatewayClient
from tailmate.adapters.db_gateway.conversation_store import GatewayConversationStore
from tailmate.adapters.db_gateway.dog_profile import GatewayDogProfileDBAdapter
from tailmate.adapters.db_gateway.media_store import GatewaySanitizedMediaStore
from tailmate.adapters.database.audit_logger import DatabaseAuditLogger
from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.conversation_store import DatabaseConversationStore
from tailmate.adapters.database.media_asset_store import DatabaseMediaAssetStore
from tailmate.adapters.conversational_responder import GeminiConversationalResponder
from tailmate.adapters.dog_profile.db_adapter import DatabaseDogProfileDBAdapter
from tailmate.adapters.dog_profile.extractors import (
    CompositeExtractor,
    GeminiStructuredExtractorClient,
    LLMFlashExtractor,
    LLMProExtractor,
    RuleBasedExtractor,
)
from tailmate.adapters.gcs.gcs_adapter import GcsBlobStore
from tailmate.adapters.knowledge_base import (
    GatewayKnowledgeRetriever,
    GeminiKnowledgeAnswerClient,
    PgVectorKnowledgeRetriever,
    VertexTextEmbeddingClient,
)
from tailmate.adapters.localfs.blob_store import LocalBlobStore
from tailmate.adapters.media.audio_transcriber import GeminiAudioTranscriber
from tailmate.adapters.media.sanitized_media_store import DirectSanitizedMediaStore
from tailmate.adapters.vertex_agent_engine.observability import CloudObservability
from tailmate.agent_runtime.ports.conversational_responder import ConversationalResponder
from tailmate.agent_runtime.ports.dog_profile_db_adapter import DogProfileDBAdapter
from tailmate.agent_runtime.ports.intent_classifier import IntentClassifier
from tailmate.agent_runtime.ports.knowledge_retriever import KnowledgeRetriever
from tailmate.agent_runtime.ports.profile_extractor import ProfileExtractor
from tailmate.agent_runtime.ports.session_store import SessionStore
from tailmate.agent_runtime.ports.sanitized_media_store import SanitizedMediaStore
from tailmate.agent_runtime.ports.audio_transcriber import AudioTranscriber
from tailmate.agent_runtime.services.agent_factory import build_root_orchestrator
from tailmate.agent_runtime.services.hybrid_intent_classifier import HybridIntentClassifier
from tailmate.agent_runtime.services.llm_intent_classifier import LLMIntentClassifier
from tailmate.agent_runtime.services.rule_based_intent_classifier import RuleBasedIntentClassifier
from tailmate.agent_runtime.ports.blob_store import BlobStore
from tailmate.agent_runtime.services.graph_orchestrator import GraphOrchestrator
from tailmate.bootstrap.config import (
    AppConfig,
    AppEnvironment,
    ExtractionStrategy,
    IntentClassifierStrategy,
)
from tailmate.contracts.errors import ConfigurationError
from tailmate.contracts.audit import AuditLogger
from tailmate.skills.registry import InMemorySkillRegistry, register_discovered_skills
from sqlalchemy.engine import URL


SECRET_MANAGER_RESOURCE_PREFIX = "projects/"  # nosec B105


def is_secret_manager_reference(value: str) -> bool:
    """Return whether a config value is a Secret Manager resource name."""

    return value.startswith(SECRET_MANAGER_RESOURCE_PREFIX) and "/secrets/" in value


@dataclass
class AppContainer:
    """Composes the runtime from configuration, adapters, and registries."""

    config: AppConfig
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)
    _engine_factory: DatabaseEngineFactory | None = field(default=None, init=False, repr=False)
    _audit_logger: AuditLogger | None = field(default=None, init=False, repr=False)
    _db_gateway_client: DbGatewayClient | None = field(default=None, init=False, repr=False)
    _session_store: SessionStore | None = field(default=None, init=False, repr=False)
    _blob_store: BlobStore | None = field(default=None, init=False, repr=False)
    _media_asset_store: DatabaseMediaAssetStore | None = field(default=None, init=False, repr=False)
    _dog_profile_db_adapter: DogProfileDBAdapter | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _knowledge_retriever: KnowledgeRetriever | None = field(default=None, init=False, repr=False)
    _conversational_responder: ConversationalResponder | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _profile_extractor: ProfileExtractor | None = field(default=None, init=False, repr=False)
    _sanitized_media_store: SanitizedMediaStore | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _audio_transcriber: AudioTranscriber | None = field(default=None, init=False, repr=False)
    _intent_classifier: IntentClassifier | None = field(default=None, init=False, repr=False)
    _observability: CloudObservability | None = field(default=None, init=False, repr=False)
    _skill_registry: InMemorySkillRegistry | None = field(default=None, init=False, repr=False)
    _orchestrator: GraphOrchestrator | None = field(default=None, init=False, repr=False)
    _secret_client: secretmanager.SecretManagerServiceClient | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def _build_secret_client(self) -> secretmanager.SecretManagerServiceClient:
        with self._lock:
            if self._secret_client is None:
                self._secret_client = secretmanager.SecretManagerServiceClient()
            return self._secret_client

    def _resolve_secret_value(self, raw_value: str, *, variable_name: str) -> str:
        """Resolve a plain value or Secret Manager reference into the actual secret."""

        if not is_secret_manager_reference(raw_value):
            return raw_value
        try:
            response = self._build_secret_client().access_secret_version(
                request={"name": raw_value}
            )
        except Exception as exc:
            raise ConfigurationError(
                f"{variable_name} points to Secret Manager but could not be resolved."
            ) from exc
        return response.payload.data.decode("utf-8")

    def _get_actual_password(self) -> str:
        if self.config.db_password is None:
            raise ConfigurationError("TAILMATE_DB_PASSWORD is required for direct database access.")
        raw_password = self.config.db_password.get_secret_value().strip()
        return self._resolve_secret_value(raw_password, variable_name="TAILMATE_DB_PASSWORD")

    def _get_actual_gemini_api_key(self) -> str | None:
        """Resolve the Gemini API key, including Secret Manager references."""

        if self.config.gemini_api_key is None:
            return None
        raw_api_key = self.config.gemini_api_key.get_secret_value().strip()
        if not raw_api_key:
            return None
        return self._resolve_secret_value(
            raw_api_key,
            variable_name="TAILMATE_GEMINI_API_KEY",
        ).strip()

    def _get_vertex_ai_credentials(self):
        """Return ADC credentials for Vertex AI when available."""

        try:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        except DefaultCredentialsError:
            return None
        return credentials

    def build_database_url(self) -> str:
        """Builds the runtime database URL from atomic configuration fields."""

        if self.config.uses_db_gateway:
            raise ConfigurationError(
                "TAILMATE_DB_GATEWAY_URL is configured, so direct database URLs are disabled."
            )
        host = (
            self.config.local_tunnel_host
            if self.config.environment is AppEnvironment.LOCAL
            else self.config.db_ip
        )
        port = (
            self.config.local_tunnel_port
            if self.config.environment is AppEnvironment.LOCAL
            else 5432
        )
        return URL.create(
            drivername="postgresql+psycopg2",
            username=self.config.db_user,
            password=self._get_actual_password(),
            host=host,
            port=port,
            database=self.config.db_name,
        ).render_as_string(hide_password=False)

    def build_database_connect_args(self) -> dict[str, object]:
        """Build driver-level connect arguments for bounded database startup."""

        if self.config.uses_db_gateway:
            raise ConfigurationError(
                "TAILMATE_DB_GATEWAY_URL is configured, so direct database connect args are disabled."
            )
        connect_args: dict[str, object] = {
            "connect_timeout": self.config.db_connect_timeout_seconds,
            "application_name": self.config.agent_name,
        }
        if self.config.db_sslmode:
            connect_args["sslmode"] = self.config.db_sslmode
        return connect_args

    def build_db_gateway_client(self) -> DbGatewayClient:
        with self._lock:
            if self._db_gateway_client is None:
                if not self.config.db_gateway_url:
                    raise ConfigurationError(
                        "TAILMATE_DB_GATEWAY_URL is required when building the gateway client."
                    )
                self._db_gateway_client = DbGatewayClient(
                    gateway_url=self.config.db_gateway_url,
                    timeout_seconds=self.config.db_gateway_timeout_seconds,
                )
            return self._db_gateway_client

    def build_engine_factory(self) -> DatabaseEngineFactory:
        with self._lock:
            if self._engine_factory is None:
                self._engine_factory = DatabaseEngineFactory(
                    self.build_database_url(),
                    connect_args=self.build_database_connect_args(),
                )
            return self._engine_factory

    def build_session_store(self) -> SessionStore:
        with self._lock:
            if self._session_store is None:
                if self.config.uses_db_gateway:
                    self._session_store = GatewayConversationStore(
                        client=self.build_db_gateway_client()
                    )
                else:
                    self._session_store = DatabaseConversationStore(
                        engine_factory=self.build_engine_factory()
                    )
            return cast(SessionStore, self._session_store)

    def build_audit_logger(self) -> AuditLogger:
        with self._lock:
            if self._audit_logger is None:
                self._audit_logger = DatabaseAuditLogger(
                    engine_factory=self.build_engine_factory()
                )
            return self._audit_logger

    def build_blob_store(self) -> BlobStore:
        with self._lock:
            if self._blob_store is None:
                if self.config.environment is AppEnvironment.LOCAL:
                    self._blob_store = LocalBlobStore(root_dir=Path(self.config.local_media_root))
                else:
                    self._blob_store = GcsBlobStore(
                        bucket_name=self.config.media_bucket or "",
                        project_id=self.config.project_id,
                    )
            return self._blob_store

    def build_media_asset_store(self) -> DatabaseMediaAssetStore:
        with self._lock:
            if self._media_asset_store is None:
                self._media_asset_store = DatabaseMediaAssetStore(
                    engine_factory=self.build_engine_factory()
                )
            return self._media_asset_store

    def build_dog_profile_db_adapter(self) -> DogProfileDBAdapter:
        with self._lock:
            if self._dog_profile_db_adapter is None:
                if self.config.uses_db_gateway:
                    self._dog_profile_db_adapter = GatewayDogProfileDBAdapter(
                        client=self.build_db_gateway_client()
                    )
                else:
                    self._dog_profile_db_adapter = DatabaseDogProfileDBAdapter(
                        engine_factory=self.build_engine_factory(),
                        audit_logger=self.build_audit_logger(),
                    )
            return self._dog_profile_db_adapter

    def build_profile_extractor(self) -> ProfileExtractor:
        with self._lock:
            if self._profile_extractor is None:
                flash_extractor: LLMFlashExtractor | None = None
                pro_extractor: LLMProExtractor | None = None
                api_key = self._get_actual_gemini_api_key()
                credentials = None if api_key else self._get_vertex_ai_credentials()
                if api_key or credentials is not None:
                    flash_extractor = LLMFlashExtractor(
                        client=GeminiStructuredExtractorClient(
                            model_name=self.config.gemini_flash_model,
                            project_id=self.config.project_id,
                            location=self.config.gemini_location,
                            api_key=api_key,
                            credentials=credentials,
                            timeout_seconds=self.config.gemini_timeout_seconds,
                        )
                    )
                    pro_extractor = LLMProExtractor(
                        client=GeminiStructuredExtractorClient(
                            model_name=self.config.gemini_pro_model,
                            project_id=self.config.project_id,
                            location=self.config.gemini_location,
                            api_key=api_key,
                            credentials=credentials,
                            timeout_seconds=self.config.gemini_timeout_seconds,
                        )
                    )
                strategy = self.config.extraction_strategy
                if strategy is ExtractionStrategy.RULE:
                    self._profile_extractor = RuleBasedExtractor()
                elif strategy is ExtractionStrategy.FLASH:
                    if flash_extractor is None:
                        raise ConfigurationError(
                            "Vertex AI ADC or TAILMATE_GEMINI_API_KEY is required for the flash "
                            "extraction strategy."
                        )
                    self._profile_extractor = flash_extractor
                elif strategy is ExtractionStrategy.PRO:
                    if pro_extractor is None:
                        raise ConfigurationError(
                            "Vertex AI ADC or TAILMATE_GEMINI_API_KEY is required for the pro "
                            "extraction strategy."
                        )
                    self._profile_extractor = pro_extractor
                else:
                    self._profile_extractor = CompositeExtractor(
                        rule_extractor=RuleBasedExtractor(),
                        flash_extractor=flash_extractor,
                    )
            return self._profile_extractor

    def build_knowledge_retriever(self) -> KnowledgeRetriever | None:
        with self._lock:
            if not self.config.kb_enabled:
                return None
            if self._knowledge_retriever is None:
                api_key = self._get_actual_gemini_api_key()
                credentials = None if api_key else self._get_vertex_ai_credentials()
                if api_key is None and credentials is None:
                    raise ConfigurationError(
                        "Vertex AI ADC or TAILMATE_GEMINI_API_KEY is required when "
                        "TAILMATE_KB_ENABLED=true."
                    )
                embedding_client = VertexTextEmbeddingClient(
                    model_name=self.config.embedding_model,
                    project_id=self.config.project_id,
                    location=self.config.location,
                    api_key=api_key,
                    credentials=credentials,
                )
                answer_client = GeminiKnowledgeAnswerClient(
                    model_name=self.config.gemini_flash_model,
                    project_id=self.config.project_id,
                    location=self.config.gemini_location,
                    api_key=api_key,
                    credentials=credentials,
                    timeout_seconds=self.config.gemini_timeout_seconds,
                )
                if self.config.uses_db_gateway:
                    self._knowledge_retriever = GatewayKnowledgeRetriever(
                        client=self.build_db_gateway_client(),
                        embedding_client=embedding_client,
                        answer_client=answer_client,
                        similarity_threshold=self.config.kb_threshold,
                    )
                else:
                    self._knowledge_retriever = PgVectorKnowledgeRetriever(
                        engine_factory=self.build_engine_factory(),
                        embedding_client=embedding_client,
                        answer_client=answer_client,
                        similarity_threshold=self.config.kb_threshold,
                    )
            return self._knowledge_retriever

    def build_conversational_responder(self) -> ConversationalResponder | None:
        with self._lock:
            if self._conversational_responder is None:
                api_key = self._get_actual_gemini_api_key()
                credentials = None if api_key else self._get_vertex_ai_credentials()
                if api_key is None and credentials is None:
                    return None
                self._conversational_responder = GeminiConversationalResponder(
                    model_name=self.config.gemini_flash_model,
                    project_id=self.config.project_id,
                    location=self.config.gemini_location,
                    api_key=api_key,
                    credentials=credentials,
                    timeout_seconds=self.config.gemini_timeout_seconds,
                )
            return self._conversational_responder

    def build_intent_classifier(self) -> IntentClassifier:
        with self._lock:
            if self._intent_classifier is None:
                rule_classifier = RuleBasedIntentClassifier(self.build_skill_registry())
                strategy = self.config.intent_classifier_strategy
                if strategy is IntentClassifierStrategy.RULE:
                    self._intent_classifier = rule_classifier
                else:
                    llm_classifier = self._build_llm_intent_classifier()
                    if strategy is IntentClassifierStrategy.LLM:
                        self._intent_classifier = llm_classifier or rule_classifier
                    else:
                        self._intent_classifier = HybridIntentClassifier(
                            skill_registry=self.build_skill_registry(),
                            rule_classifier=rule_classifier,
                            llm_classifier=llm_classifier,
                            confidence_threshold=self.config.intent_llm_confidence_threshold,
                        )
            return self._intent_classifier

    def _build_llm_intent_classifier(self) -> LLMIntentClassifier | None:
        api_key = self._get_actual_gemini_api_key()
        credentials = None if api_key else self._get_vertex_ai_credentials()
        if api_key is None and credentials is None:
            return None
        return LLMIntentClassifier(
            skill_registry=self.build_skill_registry(),
            model_name=self.config.gemini_flash_model,
            project_id=self.config.project_id,
            location=self.config.gemini_location,
            dog_profile_db_adapter=self.build_dog_profile_db_adapter(),
            api_key=api_key,
            credentials=credentials,
            timeout_seconds=self.config.gemini_timeout_seconds,
        )

    def build_observability(self) -> CloudObservability:
        with self._lock:
            if self._observability is None:
                self._observability = CloudObservability(environment=self.config.environment)
            return self._observability

    def build_audio_transcriber(self) -> AudioTranscriber | None:
        with self._lock:
            if self._audio_transcriber is None:
                api_key = self._get_actual_gemini_api_key()
                credentials = None if api_key else self._get_vertex_ai_credentials()
                if api_key is None and credentials is None:
                    return None
                self._audio_transcriber = GeminiAudioTranscriber(
                    model_name=self.config.audio_transcription_model,
                    project_id=self.config.project_id,
                    location=self.config.gemini_location,
                    api_key=api_key,
                    credentials=credentials,
                    timeout_seconds=self.config.gemini_timeout_seconds,
                )
            return self._audio_transcriber

    def build_sanitized_media_store(self) -> SanitizedMediaStore:
        with self._lock:
            if self._sanitized_media_store is None:
                if self.config.environment is AppEnvironment.LOCAL:
                    self._sanitized_media_store = DirectSanitizedMediaStore(
                        blob_store=self.build_blob_store(),
                        media_asset_store=self.build_media_asset_store(),
                        dog_profile_db_adapter=self.build_dog_profile_db_adapter(),
                        audio_transcriber=self.build_audio_transcriber(),
                    )
                elif self.config.uses_db_gateway:
                    self._sanitized_media_store = GatewaySanitizedMediaStore(
                        client=self.build_db_gateway_client()
                    )
                else:
                    raise ConfigurationError(
                        "CLOUD environment without TAILMATE_DB_GATEWAY_URL cannot support "
                        "strip_metadata. Configure TAILMATE_DB_GATEWAY_URL or disable "
                        "strip_metadata via TAILMATE_DISABLED_SKILLS."
                    )
            return self._sanitized_media_store

    def build_skill_registry(self) -> InMemorySkillRegistry:
        with self._lock:
            if self._skill_registry is None:
                self._skill_registry = register_discovered_skills(
                    InMemorySkillRegistry(),
                    dependency_resolver=self.resolve_skill_dependency,
                    enabled_skill_ids=self.config.enabled_skill_ids,
                    disabled_skill_ids=self.config.disabled_skill_ids,
                )
            return self._skill_registry

    def resolve_skill_dependency(self, dependency_name: str):
        """Resolve a declared skill dependency through the container builder convention."""

        builder = getattr(self, f"build_{dependency_name}", None)
        if not callable(builder):
            return None
        return builder()

    def build_orchestrator(self) -> GraphOrchestrator:
        with self._lock:
            if self._orchestrator is None:
                session_store = self.build_session_store()
                observability = self.build_observability()
                skill_registry = self.build_skill_registry()
                _ = self.build_blob_store()
                self._orchestrator = build_root_orchestrator(
                    session_store=session_store,
                    observability=observability,
                    skill_registry=skill_registry,
                    dog_profile_db_adapter=self.build_dog_profile_db_adapter(),
                    knowledge_retriever=self.build_knowledge_retriever(),
                    conversational_responder=self.build_conversational_responder(),
                    intent_classifier=self.build_intent_classifier(),
                )
            return self._orchestrator
