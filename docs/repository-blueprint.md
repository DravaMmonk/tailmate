# Tailmate Repository Blueprint

Version: `v0.16.0`
Status: Canonical repository map for the active development baseline

This document defines the canonical repository layout for the Tailmate codebase.
It is the concrete implementation of the architecture rules in `docs/development-spec.md`.
The structure described here is already present in the repository and must be treated as the approved development baseline instead of a draft target.

## Baseline Interpretation

The repository currently contains a minimal but intentional skeleton.
That means:

- directories and ownership boundaries are considered final
- missing business logic should be added inside existing seams
- parallel top-level architecture should not be introduced
- frozen zones defined in `docs/development-spec.md` must remain stable
- all committed documentation, comments, and code within this structure must use English only
- implementation status must be described honestly; scaffold modules are allowed inside the development baseline so long as their ownership and contracts are explicit

## Scope

This file is a versioned spec under the documentation policy in `docs/development-spec.md`.

Any Pull Request that changes repository ownership, adds a new durable top-level directory, or reassigns file responsibilities must update this document in the same Pull Request.

## Repository Tree

```text
tailmate-app/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── CONTRIBUTING.md
├── docs/
│   ├── adr-0001-reject-direct-gcs-upload-and-firestore.md
│   ├── adr-0002-public-api-versioning-strategy.md
│   ├── adr-0003-hard-delete-user-privacy-requests.md
│   ├── development-spec.md
│   ├── database-migration-runbook.md
│   ├── design-spec.md
│   ├── tailmate-web-frontend-slice.md
│   ├── business-metrics-slice.md
│   ├── identity-gateway-slice.md
│   ├── knowledge-base-slice.md
│   ├── observability-slice.md
│   ├── privacy-compliance-slice.md
│   ├── public-rate-limit-slice.md
│   ├── repository-blueprint.md
│   ├── whatsapp-evolution-slice.md
│   ├── strip-metadata-slice.md
│   └── dog-profile-slice.md
├── deployment/
│   └── agent_engine/
│       └── README.md
├── vercel.json
├── tailmate-db-gateway/
│   ├── cloudbuild.yaml
│   ├── Dockerfile
│   ├── README.md
│   ├── main.py
│   └── requirements.txt
├── tailmate-whatsapp-adapter/
│   ├── cloudbuild.yaml
│   ├── Dockerfile
│   ├── README.md
│   ├── main.py
│   └── requirements.txt
├── tailmate-web/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   ├── contexts/
│   │   ├── hooks/
│   │   ├── lib/
│   │   ├── pages/
│   │   └── types/
│   ├── README.md
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── vite.config.ts
├── tailmate-vertex-test-ui/
│   ├── cloudbuild.yaml
│   ├── Dockerfile
│   ├── README.md
│   ├── main.py
│   └── requirements.txt
├── infra/
│   └── network/
│       └── README.md
├── src/
│   └── tailmate/
│       ├── __init__.py
│       ├── metrics.py
│       ├── observability.py
│       ├── tracing.py
│       ├── bootstrap/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   └── container.py
│       ├── contracts/
│       │   ├── __init__.py
│       │   ├── constants.py
│       │   ├── dog_profile.py
│       │   ├── errors.py
│       │   ├── knowledge.py
│       │   └── types.py
│       ├── agent_runtime/
│       │   ├── __init__.py
│       │   ├── models/
│       │   │   ├── __init__.py
│       │   │   ├── agent_spec.py
│       │   │   ├── session_context.py
│       │   │   └── skill_spec.py
│       │   ├── current_context.py
│       │   ├── ports/
│       │   │   ├── __init__.py
│       │   │   ├── audio_transcriber.py
│       │   │   ├── blob_store.py
│       │   │   ├── dog_profile_db_adapter.py
│       │   │   ├── knowledge_retriever.py
│       │   │   ├── memory_store.py
│       │   │   ├── observability.py
│       │   │   ├── profile_extractor.py
│       │   │   ├── sanitized_media_store.py
│       │   │   ├── session_store.py
│       │   │   ├── skill_registry.py
│       │   │   └── tool.py
│       │   └── services/
│       │       ├── __init__.py
│       │       ├── agent_factory.py
│       │       ├── graph_orchestrator.py
│       │       ├── session_service.py
│       │       ├── skill_loader.py
│       │       ├── turn_messages.json
│       │       └── turn_messages.py
│       ├── agents/
│       │   ├── __init__.py
│       │   └── root/
│       │       ├── __init__.py
│       │       ├── agent.py
│       │       ├── assembly.py
│       │       └── prompts.py
│       ├── skills/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── definition.py
│       │   ├── registry.py
│       │   ├── dog_profile/
│       │   │   ├── __init__.py
│       │   │   ├── manifest.py
│       │   │   └── skill.py
│       │   ├── strip_metadata/
│       │   │   ├── __init__.py
│       │   │   ├── manifest.py
│       │   │   └── skill.py
│       │   └── strip_metadata_skill.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── database/
│       │   │   ├── __init__.py
│       │   │   ├── conversation_store.py
│       │   │   ├── engine_factory.py
│       │   │   ├── media_asset_store.py
│       │   │   ├── models.py
│       │   │   └── migrations/
│       │   │       ├── README.md
│       │   │       ├── env.py
│       │   │       ├── script.py.mako
│       │   │       └── versions/
│       │   │           ├── a72d9c5f4e11_add_knowledge_chunks_table_for_verified_.py
│       │   │           ├── c1e9f6a3b2d4_add_public_query_rate_limit_events.py
│       │   │           └── README.md
│       │   ├── gcs/
│       │   │   ├── __init__.py
│       │   │   └── gcs_adapter.py
│       │   ├── media/
│       │   │   ├── __init__.py
│       │   │   ├── audio_transcriber.py
│       │   │   └── sanitized_media_store.py
│       │   ├── localfs/
│       │   │   ├── __init__.py
│       │   │   └── blob_store.py
│       │   ├── network/
│       │   │   ├── __init__.py
│       │   │   └── vpc_access.py
│       │   ├── whatsapp/
│       │   │   ├── __init__.py
│       │   │   ├── app.py
│       │   │   ├── config.py
│       │   │   └── evolution_api.py
│       │   ├── db_gateway/
│       │   │   ├── __init__.py
│       │   │   ├── client.py
│       │   │   ├── conversation_store.py
│       │   │   ├── dog_profile.py
│       │   │   ├── gateway_app.py
│       │   │   ├── identity.py
│       │   │   ├── privacy.py
│       │   │   ├── rate_limiter.py
│       │   │   └── media_store.py
│       │   ├── knowledge_base/
│       │   │   ├── __init__.py
│       │   │   ├── management.py
│       │   │   └── retriever.py
│       │   ├── dog_profile/
│       │   │   ├── __init__.py
│       │   │   ├── data/
│       │   │   ├── db_adapter.py
│       │   │   └── extractors.py
│       │   └── vertex_agent_engine/
│       │       ├── __init__.py
│       │       ├── agent_app.py
│       │       ├── observability.py
│       │       └── session_store.py
│       └── entrypoints/
│           ├── __init__.py
│           ├── cli.py
│           ├── deploy.py
│           ├── kb.py
│           ├── local_demo.py
│           ├── local_dev.py
│           ├── new_skill.py
│           ├── root_app.py
│           └── vertex_test_ui.py
└── tests/
    ├── contract/
    │   └── README.md
    ├── integration/
    │   └── README.md
    └── unit/
        ├── README.md
        └── test_vertex_test_ui.py
```

## File Responsibilities

### `docs/`

- `docs/adr-0001-reject-direct-gcs-upload-and-firestore.md`
  Accepted architecture decision record for the current storage and persistence baseline, including the rejection of direct-to-GCS signed uploads and Firestore migration.
- `docs/adr-0002-public-api-versioning-strategy.md`
  Accepted architecture decision record for the `/v1/` public API boundary, future public version rollouts, and the explicit non-versioned scope of internal IAM-only routes.
- `docs/adr-0003-hard-delete-user-privacy-requests.md`
  Accepted architecture decision record for authenticated user data export plus hard-delete sequencing across PostgreSQL, blob storage, and Firebase.
- `docs/development-spec.md`
  The binding engineering standard. Review and architecture decisions must conform to it.
- `docs/database-migration-runbook.md`
  Controlled operational runbook for Alembic schema generation, staging validation, production dry-run review, rollback, and high-risk migration approval.
- `docs/design-spec.md`
  Controlled frontend design-language specification for future Tailmate web surfaces that adopt the Soft Organic visual system.
- `docs/tailmate-web-frontend-slice.md`
  Versioned slice record for the owner-facing React SPA, including route ownership, public-contract mapping, and implementation boundaries against the current backend surface.
- `docs/repository-blueprint.md`
  The canonical directory map and file ownership guide for the repository.
- `docs/identity-gateway-slice.md`
  Versioned slice record for the Firebase-backed public ingress and owner-isolation rollout, including deferred sharing-schema notes.
- `docs/privacy-compliance-slice.md`
  Versioned slice record for public privacy export and hard-delete workflows, including snapshot shape and external cleanup sequencing.
- `docs/observability-slice.md`
  Versioned slice record for request-correlated structured logging across the agent runtime, DB gateway, and WhatsApp adapter.
- `docs/public-rate-limit-slice.md`
  Versioned slice record for the public `/v1/agent/query` sliding-window rate limit, including thresholds and over-limit behavior.
- `docs/knowledge-base-slice.md`
  Versioned slice record for the verified knowledge base orchestrator-port fallback path, including direct and gateway retrieval modes.
- `docs/whatsapp-evolution-slice.md`
  Versioned slice record for the WhatsApp Evolution adapter, bridge-side auto-provisioning, and external-channel deployment path.
- `docs/strip-metadata-slice.md`
  Versioned slice record for the `strip_metadata` business release, including cognition, action, memory, and validation expectations.
- `docs/dog-profile-slice.md`
  Versioned slice record for the `dog_profile` business release, including the progressive-profile contract, extraction strategies, and validation expectations.

### `.github/`

- `ISSUE_TEMPLATE/*.md`
  English-only GitHub issue templates for bugs and feature requests.
- `PULL_REQUEST_TEMPLATE.md`
  Pull Request template aligned with the repository changelog, versioning, validation, and language rules.

### `CONTRIBUTING.md`

- `CONTRIBUTING.md`
  Contributor-facing summary of branch naming, pre-1.0 semantic versioning, changelog updates, GitHub Flow, and English-language collaboration rules.

### `deployment/`

- `deployment/agent_engine/README.md`
  Deployment contract for Vertex AI Agent Engine. Documents packaging rules, deployment entrypoint, and release expectations.
- `deployment/agent_engine/requirements.txt`
  Generated deployment dependency manifest exported from `uv.lock`. This is the parity file for Agent Engine deployment bundles.

### `vercel.json`

- `vercel.json`
  Repository-owned Vercel preview configuration that builds the owner-facing SPA from `tailmate-web/` and rewrites all routes to the static `index.html` entrypoint.

### `tailmate-db-gateway/`

- `cloudbuild.yaml`
  Canonical Cloud Build recipe for building the gateway image from the repository root while using the gateway Dockerfile.
- `README.md`
  Cloud Run gateway contract for session APIs, privacy export/delete, and privacy-safe media uploads.
- `main.py`
  Gateway entrypoint that loads the shared Flask app.
- `Dockerfile`
  Gateway container build contract, including ffmpeg availability for video metadata stripping.

### `tailmate-whatsapp-adapter/`

- `cloudbuild.yaml`
  Canonical Cloud Build recipe for building the WhatsApp adapter image from the repository root while using the adapter Dockerfile.
- `README.md`
  Cloud Run adapter contract for Evolution API webhooks, bridge auto-provisioning, and click-to-chat entrypoints.
- `main.py`
  Cloud Run entrypoint that loads the shared WhatsApp adapter Flask app.
- `Dockerfile`
  Adapter container build contract for the Evolution-to-gateway bridge surface.

### `tailmate-web/`

- `tailmate-web/README.md`
  Setup and ownership guide for the owner-facing React SPA.
- `tailmate-web/public/`
  Static assets for the web client.
- `tailmate-web/src/components/`
  Reusable UI building blocks, landing sections, chat surfaces, and layout primitives for the SPA.
- `tailmate-web/src/contexts/`
  Firebase-authenticated owner identity and locally persisted chat-session state.
- `tailmate-web/src/hooks/`
  Frontend-facing domain hooks that compose auth, export recovery, and SSE query behavior.
- `tailmate-web/src/lib/`
  Public API client helpers, Firebase bootstrap, constants, and local persistence helpers.
- `tailmate-web/src/pages/`
  Route-level compositions for the landing page, login, dashboard, chat, and settings.
- `tailmate-web/src/types/`
  Frontend-owned contract types for public gateway and adapter responses.
- `tailmate-web/index.html`
  Vite HTML entrypoint for the SPA.
- `tailmate-web/package.json`
  Frontend dependency and script manifest.
- `tailmate-web/tailwind.config.ts`
  Tailwind CSS configuration for the owner-facing SPA.
- `tailmate-web/tsconfig.json`
  TypeScript project entry configuration for the SPA.
- `tailmate-web/vite.config.ts`
  Vite build configuration for the SPA.

### `tailmate-vertex-test-ui/`

- `cloudbuild.yaml`
  Canonical Cloud Build recipe for building the browser test UI image from the repository root while using the test UI Dockerfile.
- `README.md`
  Cloud Run test UI contract for browser-based Agent Engine smoke testing and environment isolation.
- `main.py`
  Cloud Run entrypoint that loads the shared Vertex test UI Flask app.
- `Dockerfile`
  Test UI container build contract for the lightweight browser smoke-test surface.

### `infra/`

- `infra/network/README.md`
  Infrastructure boundary for Private Service Connect based private connectivity assumptions.

### `src/tailmate/bootstrap/`

- `config.py`
  Single source of truth for application configuration, environment parsing, deployment settings, atomic database credentials, and deployment-side validation such as secret masking, network attachment validation, and DNS peering completeness checks.
- `container.py`
  Dependency assembly root. Wires configuration, adapters, skill registry, assembles the database URL from atomic fields, and builds the root orchestrator without breaking constructor serialization safety.

### `src/tailmate/`

- `metrics.py`
  Shared business-metrics registry and Prometheus text exporter used by runtime hooks, adapters, and the internal metrics endpoint.
- `observability.py`
  Shared structured logging helpers, including the request-scoped log context, JSON formatter, root logger configuration, and request-id generation utilities.
- `tracing.py`
  Shared OpenTelemetry tracing helpers, W3C trace-context propagation, and span configuration used across the gateway, runtime, and adapters.

### `src/tailmate/contracts/`

- `constants.py`
  Shared architectural constants and well-known names.
- `dog_profile.py`
  The Pydantic SSOT for persisted dog-profile records, creation and enrichment contracts, and extraction results.
- `errors.py`
  Shared exception types for runtime, orchestration, and adapter boundaries.
- `knowledge.py`
  The Pydantic SSOT for verified knowledge base query input, query output, and search-hit contracts.
- `types.py`
  Reusable typed payloads for query input, query output, and runtime metadata.

### `src/tailmate/agent_runtime/models/`

- `agent_spec.py`
  Declarative agent definition. Holds identity, model, orchestrator binding, and attached skills.
- `session_context.py`
  Typed representation of persisted conversation state loaded from the database.
- `skill_spec.py`
  Declarative skill contract. Defines skill id, capability description, required tools, and attachment metadata.

### `src/tailmate/agent_runtime/ports/`

- `audio_transcriber.py`
  Abstract interface for sanitized audio transcription so media ingestion does not couple directly to one Gemini implementation.
- `blob_store.py`
  Abstract interface for media and binary asset storage. The orchestrator and skills use this instead of cloud SDKs.
- `dog_profile_db_adapter.py`
  Business persistence contract for owner-scoped dog-profile reads and writes.
- `knowledge_retriever.py`
  Business port for verified knowledge retrieval. It is an orchestrator fallback path, not a registered skill.
- `sanitized_media_store.py`
  Business-level contract for stripping sensitive media metadata before storage and returning only sanitized references.
- `session_store.py`
  Abstract interface for loading and saving persisted conversation context.
- `memory_store.py`
  Abstract interface for transient memory capabilities where needed, never the SSOT.
- `observability.py`
  Abstract interface for logging, tracing, and runtime instrumentation.
- `profile_extractor.py`
  Extraction contract used by the dog-profile enrichment tool without coupling the skill to one model strategy.
- `skill_registry.py`
  Abstract interface for skill discovery and resolution.
- `tool.py`
  Abstract tool contract used by the orchestrator and skills.

### `src/tailmate/agent_runtime/services/`

- `agent_factory.py`
  Builds a root agent from the canonical config, spec, registry, and adapters.
- `graph_orchestrator.py`
  The brain-level control plane. In the current baseline it is still a minimal skeleton that owns state load/save order and observability hooks.
- `session_service.py`
  Runtime helper around persisted conversation state. Normalizes session load/save behavior.
- `skill_loader.py`
  Resolves registered skills and attaches them to the runtime graph.
- `turn_messages.py`
  Locale resolution and deterministic fallback message builder for non-LLM turns, including localized field labels and fallback classification.
- `turn_messages.json`
  Checked-in localized message catalog packaged with the runtime for deterministic fallback responses, including verified knowledge base answer and out-of-scope text.

### `src/tailmate/agents/root/`

- `agent.py`
  The deployable Agent Engine custom agent class. Owns `__init__`, `set_up`, `query`, and optionally `stream_query`.
- `assembly.py`
  Root-agent assembly rules. Connects the agent class to the orchestrator and registry.
- `prompts.py`
  Root-level system instructions and shared prompt templates. Prompt scope is frozen, but the actual prompt body can evolve with approved feature slices.

### `src/tailmate/skills/`

- `base.py`
  Base protocol for all skills. Encodes the shape that every new capability must follow.
- `definition.py`
  Declarative discovery contract for auto-registered skill packages, including contract metadata and adapter dependency lists.
- `registry.py`
  The discovery-driven registry that scans skill packages, evaluates feature flags, and attaches enabled skills to the root agent.
- `dog_profile/`
  Package-style dog-profile skill with a manifest and focused create/enrich tool implementation.
- `strip_metadata/`
  The first package-style business skill, with a manifest and implementation split that demonstrates the auto-discovery contract.
- `strip_metadata_skill.py`
  Backward-compatible export shim for the strip_metadata package.

### `src/tailmate/adapters/database/`

- `engine_factory.py`
  Lazy SQLAlchemy engine factory. Prevents non-serializable connection objects from living on constructor state.
- `models.py`
  Canonical SQLAlchemy metadata for persisted runtime tables, including the `knowledge_chunks` table used by verified knowledge retrieval. Alembic imports this module as the migration truth source.
- `conversation_store.py`
  SQL-backed implementation of the conversation-storage port. Owns session load/save, turn history retrieval, and persistence error wrapping.
- `media_asset_store.py`
  Persists sanitized media references for downstream DB reads and rollback safety.
- `migrations/`
  Alembic-owned schema history for persistent runtime state, including the `media_assets` slice revision for sanitized upload tracking and the `knowledge_chunks` revision for verified knowledge retrieval.

### `src/tailmate/adapters/gcs/`

- `gcs_adapter.py`
  Google Cloud Storage implementation of the blob storage port for media assets. It resolves logical paths to cloud URIs without leaking physical addresses into the domain layer and treats missing-object deletes as already complete for retry-safe privacy erasure.

### `src/tailmate/adapters/media/`

- `audio_transcriber.py`
  Gemini-backed transcription adapter used after sanitized audio bytes have been produced.
- `sanitized_media_store.py`
  Direct local implementation of the metadata-stripping storage path. It gives the local sandbox parity with the cloud gateway flow while still respecting the blob-store port.

### `src/tailmate/adapters/db_gateway/`

- `client.py`
  HTTP client for the Cloud Run gateway, including trusted-user header propagation for owner-scoped routes plus bridge helper methods for platform-user auto-provisioning and query forwarding.
- `conversation_store.py`
  Session-store adapter backed by the Cloud Run gateway.
- `dog_profile.py`
  Gateway-backed dog-profile adapter that keeps load and enrich calls owner-scoped.
- `identity.py`
  Users-table identity resolver and internal session-id namespacing helper shared by public-ingress routes and bridge-side non-web auto-provisioning.
- `privacy.py`
  Gateway-only privacy export and erasure service that assembles owner-scoped snapshots, deletes blob-backed media objects, deletes Firebase identities, and hard-deletes relational user data.
- `rate_limiter.py`
  Gateway-only sliding-window rate limit implementations for the public `/v1/agent/query` ingress, with database-backed production storage plus an in-memory fallback used by tests.
- `media_store.py`
  Cloud adapter that forwards `strip_metadata` requests to the gateway upload endpoint.
- `gateway_app.py`
  Shared Flask app used by the Cloud Run gateway entrypoint for public Firebase ingress plus internal bridge-user, bridge-query, session, dog-profile, privacy, sanitized-media, verified knowledge search and management APIs, SSE query transport, distributed tracing, and the internal Prometheus-compatible `/metrics` export.

### `src/tailmate/adapters/knowledge_base/`

- `__init__.py`
  Export surface for the verified knowledge base adapters.
- `management.py`
  Reviewed knowledge chunk create, preview, import, delete, upload-parse, and reindex helpers for the internal KB management surface.
- `retriever.py`
  Direct PostgreSQL and Cloud Run gateway knowledge retrievers, plus the Gemini answer-synthesis client and shared fallback logic.

### `src/tailmate/adapters/whatsapp/`

- `app.py`
  Flask-based webhook adapter that normalizes Evolution payloads, auto-provisions WhatsApp identities through the internal gateway, forwards bridge queries, emits request-correlated structured logs, and returns click-to-chat plus QR entrypoint data.
- `config.py`
  Runtime settings contract for the WhatsApp adapter service, including Evolution API credentials, gateway URL, public number, webhook secret, and fallback copy.
- `evolution_api.py`
  Outbound Evolution API client used to send WhatsApp text responses back to the originating chat.

### `src/tailmate/adapters/dog_profile/`

- `db_adapter.py`
  Direct SQL dog-profile adapter that enforces owner isolation before returning or mutating persisted profiles.
- `extractors.py`
  Deterministic and Gemini-backed extraction strategies for progressive dog-profile enrichment.

### `src/tailmate/adapters/localfs/`

- `blob_store.py`
  Local filesystem implementation of the blob storage port. It resolves the same logical paths to `file://` URIs for local development.

### `src/tailmate/adapters/network/`

- `vpc_access.py`
  Network assumptions and helper wiring for Private Service Connect based private connectivity.

### `src/tailmate/adapters/vertex_agent_engine/`

- `agent_app.py`
  Vertex AI Agent Engine integration boundary. Exposes the deployable application object.
- `observability.py`
  Cloud-runtime observability adapter that emits structured JSON log events through the shared logging context.
- `session_store.py`
  Agent Engine aware session adapter. Bridges runtime session identifiers with database-backed state.

### `src/tailmate/entrypoints/`

- `cli.py`
  Developer CLI entrypoint for repository-local commands such as `tailmate new-skill`.
- `deploy.py`
  Explicit deployment entrypoint for building and publishing the agent application. Must force `CLOUD` mode before app creation.
- `kb.py`
  Developer-only KB maintenance commands such as `tailmate kb reindex` for direct-mode embedding rebuilds.
- `local_demo.py`
  Developer-facing local query harness for text and upload flows, including optional trusted-user injection for owner-scoped validation and audio-transcribed strip-metadata validation.
- `local_dev.py`
  Local development bootstrap. Must load `.env`, run sandbox pre-flight checks, and preserve the same layering when using local substitutes.
- `new_skill.py`
  Scaffold generator for new vertical-slice skills, including contracts, adapter stubs, tests, and slice documentation.
- `root_app.py`
  Module-level root application object used by source-based Agent Engine deployments.
- `vertex_test_ui.py`
  Flask-based browser test surface that reads its target Agent Engine from environment variables and forwards text or upload-backed smoke-test requests through the deployed runtime, including SSE query transport.

### `tests/`

- `tests/unit/README.md`
  Unit test scope: isolated tools, registries, and orchestration policies.
- `tests/unit/test_vertex_test_ui.py`
  Unit coverage for the Cloud Run test UI request shaping, upload handling, and runtime health responses.
- `tests/integration/README.md`
  Integration test scope: database adapter, runtime wiring, and cloud-facing boundaries.
- `tests/contract/README.md`
  Contract test scope: skill registration, query schemas, and deployable agent class behavior.
  Verified knowledge base coverage belongs in the same integration and contract scopes, not in a new skill-specific test tree.

## Mandatory Build Rule

The codebase must treat this layout as the final target structure.
New modules must be placed into these ownership boundaries instead of creating parallel folders.

## Frozen Framework Boundary

The current development baseline freezes the framework boundary at these seams:

- entrypoints choose runtime mode and bootstrap only
- bootstrap assembles dependencies only
- the root agent owns lifecycle only
- the orchestrator owns flow and state-transition order only
- verified knowledge retrieval may live in an orchestrator port when it is a read-only fallback path, but new user-facing capabilities still enter through skills
- adapters own infrastructure access only
- skills remain the only approved path for future business capabilities

Work that may continue behind the frozen boundary:

- replacing scaffold logic with real persistence, observability, and business behavior
- adding skill modules and adapter implementations inside the existing ownership map
- adding Alembic revisions under the existing migration tree

## Implementation Rule

When a new feature is added, developers must extend this blueprint in place:

- contracts go into `src/tailmate/contracts/`
- business skills go into `src/tailmate/skills/`
- persistence models and migrations go into `src/tailmate/adapters/database/`
- prompt-level capability guidance goes into `src/tailmate/agents/root/prompts.py`

If a proposed change does not fit naturally into one of these ownership boundaries, it must be treated as an architecture review item instead of normal feature work.
