# Changelog

This file records every versioned change to Tailmate.
Entries follow Keep-a-Changelog style and ship in the same PR as the implementation.

## Versioning Rules

- Tailmate is currently in active development and uses pre-1.0 semantic versioning: `0.MINOR.PATCH`
- use `0.MINOR.0` for a new feature slice or a meaningful developer-workflow capability
- use `0.MINOR.PATCH` for a bug fix, reliability update, or non-breaking documentation or operational change on the active minor line
- pre-release candidates may use `-alpha.N`, `-beta.N`, or `-rc.N`
- each changelog entry must use the exact tagged version
- each entry should include `[Added]`, `[Changed]`, `[Fixed]`, and `[Breaking Changes]` when applicable
- issue references should be included in `[Fixed]` when an issue exists

# Unreleased

- Retired the WhatsApp product surface by removing the web handoff route and CTA, rejecting the legacy gateway feature flag, and deleting the public entrypoint contract from the owner-facing application.
- Fixed the Tailmate web login page so Firebase registration configuration errors now downgrade the UI to login-only mode with an actionable setup hint instead of surfacing the raw SDK message.
- Fixed the Tailmate web `/chat` SSE client so live chat now tolerates both standard SSE framing and the currently deployed single-newline event framing instead of collapsing multiple streamed JSON payloads into `The chat stream returned an invalid event payload.`
- Fixed the shared gateway and Vertex test UI SSE formatters so emitted events now end with the required blank-line separator for spec-compliant SSE clients.
- Fixed the `main`-branch integration CI job so it no longer inherits the pull-request coverage gate when running the integration-only test suite.
- Fixed the local public gateway so a missing `public_query_rate_limit_events` table now triggers a one-time warning and an in-memory rate-limit fallback instead of crashing `/v1/agent/query` for the active process.
- Fixed the public gateway registration flow so a duplicate existing `users` row no longer aborts the surrounding PostgreSQL transaction before the `web` platform connection can be reconciled.

## v0.16.0 - 2026-03-30

### [Added]

- Added the durable `tailmate-web/` React 19 + TypeScript + Vite SPA as the owner-facing web frontend for Tailmate.
- Added the protected route set for dashboard, streaming chat, and settings plus the public landing, login, and WhatsApp redirect routes.
- Added the `docs/tailmate-web-frontend-slice.md` slice document and linked the new frontend surface from repository documentation.

### [Changed]

- Updated the web frontend to follow the repository Soft Organic design language with parchment backgrounds, forest-green / terracotta tokens, organic radii, glass navigation, grain texture, and Framer Motion entry transitions.
- Updated the frontend integration layer so Firebase auth, owner export recovery, WhatsApp entrypoint loading, and `/v1/agent/query` SSE streaming all run through the currently published public contracts.
- Updated the repository blueprint and frontend README to describe the new durable top-level frontend directory and its ownership boundaries.
- Updated preview deployment configuration so Vercel builds the static SPA from `tailmate-web/` instead of trying to infer a Flask entrypoint from the repository root.

### [Fixed]

- Fixed the missing owner-facing web delivery surface by implementing a routed SPA that can sign in, recover export state, stream live chat, and hand off to WhatsApp without relying on the internal Vertex test UI.
- Fixed the initial frontend runtime wiring by mounting the app inside `BrowserRouter` and by refreshing Firebase ID tokens for authenticated API calls instead of reusing a stale cached token.

### [Breaking Changes]

- None.

## v0.15.0 - 2026-03-29

### [Added]

- Added scoped mypy, Bandit, pip-audit, and pytest-cov development dependencies plus repository-owned tool configuration in `pyproject.toml`.
- Added pull-request security gates for static application analysis and locked runtime dependency auditing in `.github/workflows/ci.yml`.
- Added `docs/how-to-add-a-skill.md` and richer `tailmate new-skill` guidance so scaffolded skills include explicit intent and adapter-wiring next steps.
- Added `processed_webhook_events` and `audit_events` schema support plus the matching audit-logger contract and database adapter wiring.

### [Changed]

- Updated pull-request CI to run scoped mypy checks, Bandit, pip-audit against exported runtime dependencies, and unit tests with coverage before contract tests.
- Updated repository workflow documentation to describe the new static-analysis, security, and coverage expectations for local validation and pull-request readiness.
- Updated runtime dependency resolution to pin secure `requests` and `cryptography` baselines in the lockfile and deployment requirements export.
- Updated pytest coverage defaults to emit `coverage.xml`, fail below the repository baseline, and publish the coverage artifact from pull-request CI.
- Updated the WhatsApp adapter health contract so `GET /health` matches the existing deep-probe behavior exposed by `GET /healthz` and `GET /statusz`.
- Updated the migration rollback runbook and historical revisions to classify downgrade safety explicitly and block unsafe rollback boundaries with `NotImplementedError`.
- Updated gateway, runtime, and WhatsApp request correlation so `trace_id` is generated at each entry boundary, returned through `X-Trace-Id`, and threaded into downstream agent metadata and structured logs.
- Updated the WhatsApp bridge path to claim inbound webhook ids atomically before processing so Evolution retries can be acknowledged without repeating skill execution.

### [Fixed]

- Fixed issue #118 by introducing a repository-owned mypy baseline for stable typed contracts, runtime ports, and skill manifests.
- Fixed issue #119 by adding Bandit and pip-audit gates while documenting and justifying the remaining deliberate security-scan exceptions in code.
- Fixed issue #121 by publishing unit-test coverage in pull-request CI through `pytest-cov`.
- Fixed issue #122 by propagating `trace_id` through the gateway, runtime, DB gateway client, and CloudObservability structured log output.
- Fixed issue #123 by exposing `GET /health` on the WhatsApp adapter and documenting that Cloud Run probes must target the deep health route.
- Fixed issue #124 by deduplicating inbound WhatsApp webhook deliveries through an atomic processed-message claim path.
- Fixed issue #125 by recording dog-profile create and update mutations in an `audit_events` trail with `before` and `after` snapshots.
- Fixed issue #126 by keeping the public `/v1/agent/query` payload forward-compatible when callers send unknown JSON fields.
- Fixed issue #127 by centralizing request user identity and trace binding in gateway middleware while routing ownership checks through the shared authz helper.
- Fixed issue #128 by enforcing the repository coverage floor in pytest configuration and uploading `coverage.xml` from pull-request CI.
- Fixed issue #129 by upgrading the `tailmate new-skill` scaffold with an adapter-backed unit-test template, a post-generation wiring checklist, and a dedicated skill-authoring guide.
- Fixed issue #130 by classifying historical migration downgrades as data-loss or snapshot-required in code and in the rollback runbook.

### [Breaking Changes]

- None.

## v0.14.0 - 2026-03-29

### [Added]

- Added a shared business-metrics registry with Prometheus text exposition for session, skill, intent, knowledge-base, and Gemini latency metrics.
- Added the internal `/metrics` gateway endpoint for internal scraping and the business-metrics slice document to record the new contract.
- Added runtime hooks that increment the business metrics from the orchestrator, skill execution step, knowledge-base skill, and Gemini-backed adapters.
- Added SSE streaming support to `POST /v1/agent/query`, the root agent, and the Vertex test UI using `query.started`, `query.delta`, and `query.completed` events.
- Added shared OpenTelemetry tracing helpers, W3C trace-context propagation, and adapter spans across the gateway, DB gateway client, database stores, GCS, identity, privacy, and rate-limiter paths.
- Added internal KB management routes for reviewed chunk create, preview, import, delete, plus the `tailmate kb reindex` developer CLI workflow.
- Added audio upload sanitization and Gemini-backed transcription so supported voice notes can be converted into text before normal runtime routing continues.

### [Changed]

- Updated the public and bridge query gateway payloads to carry a channel label into request metadata so new session metrics can be grouped by channel.
- Updated the public gateway contract so callers can request SSE from `POST /v1/agent/query` with `Accept: text/event-stream` while preserving the existing JSON response contract by default.
- Updated gateway and runtime observability so structured logs now include trace identifiers while request metadata can carry `traceparent` and `tracestate` across service boundaries.
- Updated the verified knowledge-base slice so operators can manage reviewed chunks through narrow internal APIs instead of direct SQL-only workflows.
- Updated the strip-metadata and dog-profile flows so audio uploads are always sanitized first, optionally re-enter the standard routing pipeline as text when transcription is available, and otherwise return the normal strip-metadata success path.
- Updated the repository blueprint, root README, and gateway README to describe the internal metrics, tracing, streaming, KB management, and audio-ingestion surfaces.
- Updated GitHub Actions CI to opt into the Node 24 JavaScript-action runtime ahead of the Node 20 runner deprecation window.

### [Fixed]

- Fixed issue #108 by exposing a stable, Prometheus-compatible business-metrics surface for operators to inspect session volume, skill success and error rates, intent routing, verified KB usage, and Gemini latency.
- Fixed issue #102 by adding SSE streaming to the stable `/v1/agent/query` ingress without breaking the existing structured JSON response contract.
- Fixed issue #107 by extending the structured logging baseline into distributed tracing with OpenTelemetry spans and propagated trace context.
- Fixed issue #112 by adding operator-safe reviewed KB management APIs and a direct-mode reindex workflow on top of the verified knowledge-base slice.
- Fixed issue #111 by allowing audio uploads to pass through sanitized-media ingestion, transcription, and downstream dog-profile or fallback routing.
- Fixed the audio-query degradation gap so sanitized uploads still succeed when the optional transcriber is not configured, and fixed the streaming path so conversational SSE emits true incremental model chunks instead of post-hoc slicing a completed response.

### [Breaking Changes]

- None.

## v0.13.0 - 2026-03-29

### [Added]

- Added a dedicated public-query rate limiter with both database-backed and in-memory sliding-window implementations.
- Added the `public_query_rate_limit_events` schema plus integration coverage for persisted sliding-window behavior.
- Added the public rate-limit slice document to record the threshold, response headers, and validation path.

### [Changed]

- Updated `POST /v1/agent/query` to enforce a per-user default limit of `30` requests per `60` seconds before the request reaches Agent Engine.
- Updated the public gateway contract to return `429` with `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Window-Seconds` when the user exceeds the window.
- Updated gateway configuration and documentation to expose the public rate-limit window settings.

### [Fixed]

- Fixed issue #99 by adding per-user sliding-window rate limiting to the public `/v1/agent/query` ingress, reducing authenticated abuse risk and uncontrolled model spend.

### [Breaking Changes]

- None.

## v0.12.0 - 2026-03-29

### [Added]

- Added a shared structured logging module with JSON formatting, request-scoped log context, and generated `request_id` correlation ids.
- Added request correlation propagation through the DB gateway client plus regression coverage for request-id headers in the gateway, WhatsApp adapter, and log formatter.
- Added the observability slice document to record the structured logging contract and validation path.

### [Changed]

- Updated the DB gateway and WhatsApp adapter to accept or generate `X-Tailmate-Request-Id`, return it on responses, and emit structured request lifecycle logs with `latency_ms`.
- Updated the root agent and graph orchestrator to bind request correlation into runtime execution and to include standardized `intent`, `skill`, and `latency_ms` fields in top-level observability events.
- Updated gateway and adapter documentation to describe the structured JSON logging baseline and request correlation behavior.

### [Fixed]

- Fixed issue #106 by replacing bare or no-op cloud logging paths with structured JSON logs and request correlation across the agent runtime, DB gateway, and WhatsApp adapter.

### [Breaking Changes]

- None.

## v0.11.0 - 2026-03-29

### [Added]

- Added authenticated public privacy routes at `GET /v1/users/<user_id>/export` and `DELETE /v1/users/<user_id>` for owner-scoped data portability and erasure.
- Added the gateway privacy service plus integration coverage for exporting and hard-deleting a user's account, dog profiles, media metadata, enrichment history, and conversation sessions.
- Added ADR-0003 and the privacy-compliance slice document to record the accepted hard-delete strategy and validation path.

### [Changed]

- Updated the public gateway contract so privacy deletes now remove owned GCS media objects and the matching Firebase Authentication user before the relational hard-delete transaction commits.
- Updated the GCS blob-store delete behavior to treat missing objects as already removed, making privacy retries idempotent after partial external cleanup.
- Updated repository, identity-gateway, and gateway README documents to describe the new `/v1/` privacy lifecycle surface and the additional public gateway media-bucket requirement.

### [Fixed]

- Fixed issue #105 by implementing GDPR/privacy-aligned user data export and account deletion across PostgreSQL, blob storage, and Firebase-backed public identities.

### [Breaking Changes]

- None.

## v0.10.0 - 2026-03-29

### [Added]

- Added active-dog switching and multi-dog disambiguation to the dog-profile runtime, including a dedicated switch runtime skill, localized selection prompts, and name-based dog resolution from known owner profiles.
- Added owner-scoped dog-profile listing through the internal gateway contract so direct and gateway-backed runtimes can resolve multi-dog context consistently.
- Added unit and integration coverage for explicit dog switching, named recall-based switching, ambiguous multi-dog prompts, and the new internal dog-profile list endpoint.

### [Changed]

- Updated dog-profile orchestration to persist the canonical session `active_dog_id` while preserving the legacy `dog_id` attribute for backward compatibility.
- Updated fresh-session welcome behavior so returning multi-dog users are prompted to choose a dog instead of falling through to a generic greeting when no active dog is already selected.
- Updated the dog-profile slice and gateway contract documents to describe active-dog switching, owner-scoped profile listing, and multi-dog ambiguity handling.

### [Fixed]

- Fixed issue #104 by allowing one owner to switch between multiple dogs in conversation, carry the selected dog across turns, and receive explicit guidance when a dog-specific turn is ambiguous.

### [Breaking Changes]

- None.

## v0.9.0 - 2026-03-29

### [Added]

- Added path-versioned public ingress constants and route registration for the first stable public API family under `/v1/`.
- Added ADR-0002 to document the public path-versioning strategy, migration rules, and the boundary between public and internal gateway routes.
- Added regression coverage for the versioned public account lifecycle and public agent-query routes.

### [Changed]

- Updated the Cloud Run public gateway surface to expose `POST /v1/users/register`, `POST /v1/users/activate`, `POST /v1/users/connections/<platform>`, `DELETE /v1/users/connections/<platform>`, and `POST /v1/agent/query`.
- Updated repository, gateway, and identity-slice documentation to make `/v1/` the canonical public contract while keeping IAM-only bridge and persistence routes unversioned.

### [Fixed]

- Fixed issue #113 by moving the public account and agent-query ingress onto a versioned `/v1/` path family so later public route changes can ship without mutating the first published contract in place.

### [Breaking Changes]

- Public Firebase-protected ingress routes now live under `/v1/` instead of the previous unprefixed paths.

## v0.8.0 - 2026-03-29

### [Added]

- Added a dedicated `tailmate-whatsapp-adapter/` Cloud Run service plus `src/tailmate/adapters/whatsapp/` runtime package for Evolution API webhook intake, outbound WhatsApp messaging, and click-to-chat / QR entrypoint generation.
- Added the internal gateway `POST /bridge/users/ensure` route plus matching client and identity-resolver support so bridge services can auto-provision or reactivate active non-web platform users without Firebase.
- Added unit coverage for WhatsApp webhook normalization, bridge-side auto-provisioning, gateway client bridge helpers, and the new internal gateway route.
- Added the WhatsApp Evolution slice document and adapter deployment guide.
- Added a pull-request CI workflow that runs lint, optional type checks, unit tests, and contract tests before merge, with integration tests reserved for `main`.
- Added a production database migration runbook plus a non-destructive Cloud Build migration verification step for gateway deployments.

### [Changed]

- Updated the internal bridge surface so channel adapters can provision `whatsapp` platform users before routing turns through the existing `POST /bridge/query` path.
- Updated repository docs, blueprint ownership, and environment examples to describe the dedicated WhatsApp adapter service, its Evolution API contract, and the required gateway caller-allowlist wiring.
- Updated the gateway, Vertex test UI, and WhatsApp adapter health endpoints to return structured deep-check results instead of static `200` responses.
- Updated CI readiness by clearing the existing repository Ruff violations that would have blocked the new lint gate.

### [Fixed]

- Fixed issue #95 by implementing an Evolution API adapter layer that receives inbound WhatsApp messages, auto-registers first-contact phone numbers, forwards messages into Tailmate through the existing bridge-query contract, and sends the assistant response back through Evolution `sendText`.
- Fixed the gap where WhatsApp click-to-chat or QR onboarding would previously fail for unknown phone numbers because the internal bridge route required a pre-existing active platform binding.
- Fixed issue #97 by making the shared knowledge-base retriever base contract abstract instead of leaving a runtime `NotImplementedError` path in KB-enabled deployments.
- Fixed issue #98 by rejecting the default database password placeholder during `CLOUD` startup while preserving warning-only behavior in `LOCAL`.
- Fixed issue #100 by making `GET /health`, `GET /healthz`, and `GET /statusz` fail closed with `503` when PostgreSQL, the configured Evolution webhook endpoint, or configured DB gateway / GCS deep checks are unavailable.
- Fixed issue #101 by enforcing a 4000-character query-message cap, sanitizing upload filenames, and rejecting image/video uploads that exceed their media-type limits.
- Fixed issue #103 by adding bounded exponential-backoff retries for Gemini, Vertex embeddings, and GCS adapter calls before surfacing structured adapter failures.

### [Breaking Changes]

- None.

## v0.7.0 - 2026-03-28

### [Added]

- Added the `IntentClassifier` orchestration port together with `RuleBasedIntentClassifier`, `LLMIntentClassifier`, and `HybridIntentClassifier` implementations for runtime intent routing.
- Added runtime-skill `routing_description` metadata plus classifier-focused unit coverage for rule, hybrid, and Gemini-backed routing decisions.
- Added localized `session.welcome` and `fallback.greeting_returning` message variants plus regression coverage for proactive empty-session welcomes and returning-user greetings.

### [Changed]

- Updated the graph orchestrator, root assembly, and application container so intent classification is injected as a first-class dependency and can be selected through `TAILMATE_INTENT_CLASSIFIER`.
- Updated `turn_debug` metadata to surface the resolved intent, matched runtime skills, classifier confidence, and classifier reasoning for each turn.
- Updated runtime configuration to support `TAILMATE_INTENT_CLASSIFIER` and `TAILMATE_INTENT_LLM_CONFIDENCE_THRESHOLD` for hybrid routing rollout control.
- Updated fallback response assembly to personalize greeting responses when the active dog's name is already known, and expanded locale routing patterns for greeting detection across English, Simplified Chinese, Cantonese, Vietnamese, and Hindi.
- Updated the Cloud Run DB gateway to read its `DB_*`, project, location, auth, and upload settings through a dedicated validated `GatewayConfig` contract instead of scattered raw environment lookups.
- Updated `.env.example` and the gateway deployment guide to document the gateway-specific `DB_*` contract, `FFMPEG_BINARY`, and the canonical project/location fallback rules.

### [Fixed]

- Fixed issue #86 by adding an LLM-backed fallback path for intent classification, allowing hybrid routing to recover from phrasing that deterministic pattern rules miss while still falling back safely to rule-based decisions on low-confidence or model-error cases.
- Fixed issue #89 by routing greeting turns to a returning-user variant when a remembered dog already exists, avoiding stale onboarding prompts after profile creation.
- Fixed issue #90 by short-circuiting fresh-session empty messages to a proactive welcome response instead of running the full pipeline and leaving the chat blank.
- Fixed the DB gateway startup path so missing `DB_HOST`, `DB_USER`, `DB_PASSWORD`, or related runtime settings now fail fast with explicit validation errors instead of late raw `KeyError` crashes.

### [Breaking Changes]

- None.

## v0.6.1 - 2026-03-28

### [Added]

- Added regression coverage for Simplified Chinese possessive dog-name introductions and for runtime session persistence after dog-profile creation.

### [Changed]

- Updated runtime skill observability so `turn_debug.skill_attempted` now records the executed runtime `skill_id` values consistently across the new skill pipeline.
- Externalized the locale-aware turn-routing pattern tables from `turn_messages.py` into the packaged `turn_routing_patterns.json` resource so multilingual routing fixes can be maintained through data files instead of Python literals.

### [Fixed]

- Fixed issue #80 so Simplified Chinese turns such as `我的豆豆是...` extract `豆豆` as the dog name instead of persisting the possessive prefix as part of the stored name.
- Fixed issue #81 by preserving the created `dog_id` in session attributes through the runtime skill pipeline, allowing follow-up recall and enrichment turns to reuse the active dog automatically.
- Fixed issue #82 by recording executed runtime skills in `turn_debug.skill_attempted`, restoring useful per-turn debugging metadata for the new `SkillExecutionStep` pipeline.
- Fixed multilingual dog-profile recall routing so fact questions such as `我的狗多少岁` and `你知道关于豆豆的哪些信息` match the recall path instead of falling through to knowledge-base conversational fallback with an unverified disclaimer.

### [Breaking Changes]

- None.

## v0.6.0 - 2026-03-27

### [Added]

- Added the Firebase-protected public `POST /agent/query` ingress to the shared gateway module, including user resolution through the new `users` table and internal session namespacing as `{user_id}__{platform}__{external_session_id}`.
- Added the `users` schema, the checked-in ownership-hardening Alembic migration, and the shared identity-resolution helpers used by the public ingress.
- Added regression coverage for owner-scoped session namespacing, direct DB authorization, local media ownership checks, and the trusted-user paths in the Vertex test UI and remote smoke test.
- Added the identity-gateway slice document to record the public-ingress and owner-isolation rollout.
- Added regression coverage for verified knowledge base hit, out-of-scope, direct PostgreSQL, and Cloud Run gateway retrieval paths.
- Added the knowledge-base slice document to record the orchestrator-port fallback behavior and rollout contract.

### [Changed]

- Updated dog-profile creation and enrichment contracts so owner identity is mandatory end to end, and updated the graph orchestrator plus root-agent context bridge to require verified `metadata["user_id"]` for owner-scoped flows.
- Updated the Cloud Run DB gateway and gateway client so dog-profile and media endpoints now propagate and enforce the trusted internal `X-Tailmate-User-Id` header instead of relying on unauthenticated owner ids in request bodies.
- Updated the Vertex test UI, local demo CLI, and deployment smoke test so staged and local validations can supply a trusted user id without going through the public Firebase ingress.
- Updated the gateway and repository documentation to describe the split public-ingress versus internal-IAM deployment model for the shared gateway codebase.
- Updated the graph orchestrator to treat verified knowledge retrieval as an orchestrator port, not a registered skill, with direct PostgreSQL and Cloud Run gateway modes controlled by `TAILMATE_KB_ENABLED`, `TAILMATE_EMBEDDING_MODEL`, and `TAILMATE_KB_THRESHOLD`.
- Updated deployment and repository docs to describe the JSONL-backed `knowledge_chunks` ingest workflow and the deterministic fallback behavior for misses, low-confidence matches, and retriever failures.

### [Fixed]

- Fixed issue #13 by preventing cross-user dog-profile reads, enrichments, and sanitized-media writes across both the direct SQL path and the Cloud Run gateway path.
- Fixed the gap where public end-user traffic could not be accepted safely without exposing internal persistence routes or losing ownership boundaries.
- Fixed issue #29 by forwarding trusted `--user-id` metadata through `tailmate local-chat`, so owner-scoped dog-profile turns can reach the live local create/enrich path instead of always falling back.
- Fixed issue #43 by splitting generic fallback misses into profile-aware and post-knowledge-base follow-up buckets, with localized prompts that better reflect remembered dog context and short reference turns.
- Fixed local CLI bootstrap so migration drift in the disposable local test database is resolved automatically by resetting the schema and reapplying the current Alembic heads before local checks or chats continue.
- Fixed issue #39 by adding an orchestrator-managed dog-profile recall path, so users can ask about a remembered dog and receive a localized summary of stored profile fields.
- Fixed issue #40 by treating empty dog-profile enrich extractions as `noop`, allowing those turns to continue into knowledge-base retrieval or deterministic fallback instead of returning an empty confirmation.
- Fixed issue #41 by injecting active dog-profile context into verified knowledge-base queries, so contextual questions can reach Gemini answer synthesis with the stored breed, age, weight, and health snapshot.
- Fixed issue #42 by allowing enrich turns that also contain questions to continue into the verified knowledge-base path and return a combined enrich-plus-answer response when retrieval succeeds.
- Fixed issue #44 by augmenting short referential follow-up questions with recent assistant context and by recovering dog-name context from recent turns when pronoun-only KB questions arrive before an active dog id is set.
- Fixed issue #45 by turning dog-profile create confirmations into localized onboarding prompts that invite users to continue with breed, age, weight, and health-history details.

### [Breaking Changes]

- Internal dog-profile and media gateway endpoints now require `X-Tailmate-User-Id`, `CreateDogProfileInput.user_id` is mandatory, and owner-scoped flows return `401` or `403` instead of silently proceeding with mismatched user identity.

## v0.5.3 - 2026-03-27

### [Added]

- Added unit coverage for local bootstrap credential preflight so `flash` still requires Vertex AI ADC while `rule` and `composite` can start without Gemini credentials.
- Added coverage for the local demo and orchestrator fallback path so swallowed dog-profile errors stay user-visible instead of crashing in observability.

### [Changed]

- Updated the local developer guidance to describe strategy-aware Gemini authentication in `LOCAL`, including deterministic fallback behavior when `composite` starts without ADC.
- Updated the checked-in local Gemini defaults to use the global Vertex endpoint plus `gemini-2.5-flash`, and stopped injecting a placeholder `dog_id` into text-only local demos.

### [Fixed]

- Fixed issue #19 where `src/tailmate/entrypoints/local_dev.py` always enforced Vertex AI ADC even when the configured extraction strategy could run locally without Gemini access.
- Fixed the local `dog_profile` orchestration path so swallowed skill errors no longer crash with `CloudObservability.error() got multiple values for argument 'message'`.
- Fixed the text-only `local-demo` workflow so first-run profile creation can succeed without pre-provisioning a fake `dog_id`.

### [Breaking Changes]

- None.

## v0.5.1 - 2026-03-27

### [Added]

- Added locale-aware deterministic fallback turn messages for unsupported or non-skill turns, with catalog coverage for English, Simplified Chinese, Arabic, Vietnamese, Cantonese, and Hindi.
- Added `turn_debug` response metadata so callers can audit locale selection, fallback reasons, attempted skills, and swallowed skill errors without reading raw logs.
- Added regression coverage for locale normalization, fallback classification, dog-profile and strip-metadata turn-debug metadata, and fallback behavior when skill execution errors are swallowed.
- Added a multilingual dog-breed alias dataset for the deterministic `dog_profile` extractor, with locale-grouped aliases that flatten at runtime for constant-time matching.
- Added `extractor_locale_data.json` as the packaged locale-data source for the remaining deterministic `dog_profile` extractor strings, including keyword families, normalization tokens, and runtime-compiled regex patterns.
- Added the `tailmate-vertex-test-ui/` Cloud Run scaffold, environment-driven `vertex_test_ui` entrypoint, and unit coverage back onto the active `main` line so staged Agent Engine deployments can be exercised from a browser without exposing Google Cloud credentials.

### [Changed]

- Updated the graph orchestrator to resolve a preferred locale from request metadata, remembered session preference, or message heuristics before building non-LLM responses.
- Updated the root-agent response contract so successful queries can surface `turn_debug` alongside existing business metadata.
- Updated packaging to ship the new localized message catalog as package data.
- Updated the deterministic `dog_profile` extractor to cover expanded rule families for breed, sex, desexed state, temperament, activity level, diet, age, weight, and coarse medical facts without changing the existing `CompositeExtractor` layering.
- Updated the locale-layered `dog_profile` rule assets to carry explicit Cantonese (`yue`) coverage alongside Simplified and Traditional Chinese so the runtime-flattened matchers stay aligned with the repository's supported language set.
- Updated the `CompositeExtractor` escalation policy so medical rule hits and dog-context raw-note candidates can pass deterministic hints into Flash instead of forcing Flash to start from a blank prompt.
- Updated the mainline README and repository blueprint to document the browser test UI deployment path and its environment-isolated runtime contract.

### [Fixed]

- Removed the previous empty-response path for turns where no skill matched, so users now receive a deterministic fallback response and operators receive auditable metadata about why it was chosen.
- Fixed the deterministic `dog_profile` extractor so short name-introduction turns are no longer misclassified as enrichable raw notes.
- Fixed false-positive medication extraction on non-medical phrases such as `on a raw diet` or `on the couch`.
- Fixed the deterministic `dog_profile` extractor so `raw_note` remains a whole-message fallback only when no structured rule matched, avoiding mixed raw-note plus standardized activity or temperament outputs from the same turn.
- Restored the Vertex test UI implementation on `main` so the active branch matches the historical release notes that already described the browser smoke-test surface.

### [Breaking Changes]

- Non-skill turns now return localized fallback copy instead of an empty assistant response.

## v0.5.0 - 2026-03-27

### [Added]

- Added `CONTRIBUTING.md` plus English-only GitHub issue and Pull Request templates so the repository-level versioning, branching, and language rules are enforced where collaboration happens.

### [Changed]

- Reset the repository from the old `1.x` line to the pre-1.0 `0.x.y` line and confirmed that Tailmate is still in active development rather than at a stable public release.
- Simplified the Git workflow to `main` plus short-lived `feature/*`, `fix/*`, `docs/*`, and `chore/*` branches, and removed `release/*` from the required day-to-day delivery path.
- Clarified that Git and GitHub collaboration content must be written in English, with non-English text allowed only for intentional localization assets or language-coverage fixtures.

### [Fixed]

- Removed the policy mismatch where repository documents described a released `1.x` product while the actual project maturity is still pre-1.0.

### [Breaking Changes]

- Legacy `v1.x` version labels are no longer canonical for this repository.

## v0.4.2 - 2026-03-27

### [Added]

- Added the `tailmate-vertex-test-ui/` Cloud Run service scaffold, including Docker and Cloud Build assets, so operators can publish a browser-based smoke-test entrypoint for a specific Tailmate Agent Engine deployment.
- Added the Flask-based `vertex_test_ui` entrypoint and unit coverage for text queries, upload-driven strip-metadata requests, and runtime health reporting.

### [Changed]

- Updated the package version and release metadata so new Agent Engine deployments publish as `tailmate-v0-4-2` by default instead of reusing the previous `v0.4.1` label.
- Updated the repository deployment guidance to document the new Vertex AI test UI path and its service-account-backed Cloud Run runtime.

### [Fixed]

- Removed the need to test Tailmate through local Python snippets or direct Vertex SDK calls when operators only need a shared browser surface for staged verification.

### [Breaking Changes]

- None.

## v0.4.1 - 2026-03-27

### [Changed]

- Updated the `dog_profile` Gemini extractors to initialize Vertex AI models through ADC-backed project and region settings instead of requiring runtime API-key authentication.
- Updated the local database workflow to use `cloud-sql-proxy`, renamed the helper to `scripts/start_cloudsql_proxy.sh`, and aligned the environment examples and operator guidance on the Cloud SQL baseline.
- Updated cloud deployment guidance so direct database access is described as private-IP Cloud SQL connectivity, while gateway mode remains the preferred narrow boundary for agent persistence.

### [Fixed]

- Stopped exporting `TAILMATE_GEMINI_API_KEY` into Agent Engine runtime env vars, so cloud deployments now rely on the configured service account and Vertex AI native authentication.
- Added regression coverage for ADC-backed extractor initialization, runtime env-var packaging, and local versus cloud container wiring to reduce auth and configuration drift.
- Removed the tracked `src/.DS_Store` artifact and ignored future `.DS_Store` files so local Finder metadata does not pollute release branches.

### [Breaking Changes]

- None.

## v0.4.0 - 2026-03-26

### [Added]

- Added the `dog_profile` contracts, create/enrich tools, container wiring, and implicit orchestrator path so Tailmate can create a profile from a name and enrich it across later turns.
- Added the configurable extraction stack for dog-profile enrichment: `RuleBasedExtractor`, `LLMFlashExtractor`, `LLMProExtractor`, and the `CompositeExtractor` upgrade path controlled by `TAILMATE_EXTRACTION_STRATEGY`.
- Added the `dog_profiles` and `profile_enrichment_log` persistence model plus Alembic revision `9a78bfa8b6e2` for durable profile state and extraction observability.
- Added Cloud Run gateway business endpoints for dog-profile create, load, and enrich operations so Agent Engine can keep using the narrow gateway path in cloud mode.
- Added unit, integration, and contract coverage for extractor behavior, profile tooling, registry wiring, orchestrator auto-enrichment, gateway business endpoints, and root-agent metadata surfacing.
- Added the versioned `dog_profile` slice document.

### [Changed]

- Updated the root prompt and response metadata so the runtime now surfaces the current session `dog_id` and the latest `dog_profile` action result alongside any media-sanitization metadata.
- Updated the database metadata contract so JSON-backed dog-profile fields compile in SQLite unit tests while still using JSONB on PostgreSQL-backed runtimes.
- Updated local validation to include direct AlloyDB create → enrich → readback checks for the dog-profile slice after applying Alembic head.
- Updated Agent Engine deployment packaging so cloud runtimes now receive the full dog-profile rollout contract: extraction strategy, Gemini models, Gemini timeout, skill feature flags, and direct-database tuning env vars.
- Updated the deployment entrypoint defaults to derive the published agent display name and description from the package version instead of a stale hardcoded baseline label.

### [Fixed]

- Removed the product gap where dog-profile data had to be collected manually or through rigid forms before it could become durable runtime state.
- Prevented cloud-mode dog-profile persistence from bypassing the approved gateway boundary by adding narrow business endpoints instead of raw SQL passthrough.
- Reduced silent profile drift risk by logging every enrichment attempt with the extraction strategy and confidence used for that attempt.
- Fixed the cloud deployment gap where `TAILMATE_GEMINI_API_KEY` could not be resolved from Secret Manager even though production deployments already use secret-backed configuration for database credentials.

### [Breaking Changes]

- None.

### Cognition

- Dog-profile creation is now a minimal-input behavior, while enrichment quality can be tuned operationally through a switchable extraction strategy.

### Action

- Tailmate can now create a dog profile from a name and progressively enrich it from later conversation without forcing the user into a form flow.

### Memory

- Profile state now persists in `dog_profiles`, and every enrichment attempt is durably logged in `profile_enrichment_log` for later quality analysis.
- Production deployment metadata now stays version-aligned with `pyproject.toml`, so release labels, runtime configuration, and changelog entries describe the same shipped slice.

## v0.3.0 - 2026-03-25

### [Added]

- Added package-style skill discovery through `SKILL_DEFINITION` manifests so `src/tailmate/skills/{skill_name}/` packages can register automatically at startup.
- Added feature-flag controls for the skill registry through `TAILMATE_ENABLED_SKILLS`, `TAILMATE_DISABLED_SKILLS`, and per-skill `default_enabled`.
- Added the `tailmate new-skill <name>` developer CLI scaffold to generate contract, adapter, skill, test, and slice-document placeholders.
- Added `tailmate-db-gateway/cloudbuild.yaml` as the canonical Cloud Build recipe for the gateway image.

### [Changed]

- Converted `strip_metadata` to the new package-style skill layout while keeping the previous import path as a compatibility shim.
- Updated the container to resolve skill dependencies by the `build_{dependency_name}()` convention instead of hardcoding one registry branch per skill.
- Updated the remote smoke test to load `.env` automatically and the local tunnel helper to support an explicit `ALLOYDB_TUNNEL_REMOTE_HOST`.
- Updated the local developer workflow so the tunnel helper auto-loads repository `.env` settings and the `tailmate local-demo` CLI can exercise the current product surface without ad hoc Python snippets.
- Documented the production validation lessons from the `strip_metadata` deployment path, including service-account separation, gateway bucket permissions, and per-endpoint migration drift.

### [Fixed]

- Removed the registry bottleneck where each new skill required a hand-edited `register_builtin_skills()` branch before it could be attached to the root agent.
- Reduced rollback risk by allowing skills to be soft-disabled at the registry layer before their packages are physically removed.
- Corrected the gateway build documentation to use a working Cloud Build path for the repository-root Docker context.

### [Breaking Changes]

- None.

### Cognition

- Clarified the repository workflow so new skills declare their contracts and rollout state in one discoverable manifest instead of burying those details in manual registry edits.

### Action

- Added a discovery-driven registry, a developer scaffold command, and rollout flags that make skill activation and deactivation operational instead of ad hoc.

### Memory

- Documented and version-tracked the environment-specific validation details needed to keep deployed gateway state, bucket permissions, and database schema state aligned.

## v0.2.0 - 2026-03-25

### [Added]

- Added the `strip_metadata` shared contracts, media-sanitization port, direct local adapter, and Cloud Run gateway adapter for privacy-safe media ingestion.
- Added the `strip_metadata` skill, tool, registry wiring, and orchestrator path so the root agent can sanitize media uploads before storage.
- Added the `media_assets` persistence model, database adapter, and Alembic revision `46ecbdc4202a` so sanitized media references are durably tracked in AlloyDB.
- Added the Cloud Run gateway media-upload endpoint, with `POST /media/upload` as the canonical path and `POST /media/strip-metadata` as a compatibility alias, to strip image EXIF with Pillow and video container metadata with `ffmpeg -map_metadata -1`.
- Added unit, integration, and contract coverage for gateway uploads, local media sanitization, skill registration, and root-agent response wiring.
- Added a versioned feature slice document for `strip_metadata`.

### [Changed]

- Promoted the first business vertical slice beyond the baseline skeleton by making metadata stripping the enforced first step of the media-upload flow.
- Updated the root prompt guidance and response metadata so successful strip operations return sanitized media references to callers.
- Updated the deployment smoke test to support optional end-to-end `strip_metadata` verification from a local sample media file.
- Expanded the local development dependency contract to include the gateway test/runtime dependencies needed for Flask, pg8000, and Pillow.
- Updated the Cloud Run gateway container build to install `ffmpeg` and package the shared `src/tailmate` modules from the repository root so video metadata stripping is available in production.

### [Fixed]

- Prevented raw uploaded image and video metadata from flowing into stored media references or downstream analysis paths when the `strip_metadata` slice is used.
- Kept local and cloud validation aligned by exporting the updated Agent Engine dependency bundle directly from the lockfile after the media-sanitization dependencies changed.
- Deleted the sanitized blob again if the `media_assets` database write fails, so storage and database references do not drift.

### [Breaking Changes]

- None.

### Cognition

- Added explicit prompt-level guidance that media must pass through `strip_metadata` before storage or downstream analysis.

### Action

- Added the full `Contract -> Adapter -> Skill -> Orchestration` execution path for privacy-safe media ingestion, including Cloud Run gateway execution and local sandbox parity.

### Memory

- Updated runtime response metadata, persisted session attributes, and the new `media_assets.media_ref` records so the system surfaces sanitized media references instead of the original upload payload.

## v0.1.1 - 2026-03-25

### [Added]

- Added explicit `LOCAL` and `CLOUD` runtime modes to the application configuration contract.
- Added a module-level root application entrypoint for source-based Agent Engine packaging.
- Added the Cloud Run DB gateway fallback path for Agent Engine, including the gateway service scaffold and the ID-token-authenticated session store adapter.

### [Changed]

- Promoted the current post-baseline framework to the official `v0.1.1` runnable development milestone.
- Updated the local development entrypoint to auto-load `.env`, run tunnel and ADC pre-flight checks, and bootstrap in `LOCAL` mode.
- Updated the deployment entrypoint to force `CLOUD` mode before creating the deployable agent application and to support either direct PSC database access or the Cloud Run gateway path.
- Documented the runtime mode behavior, filesystem-backed local storage contract, deployment model, and gateway troubleshooting guidance across the spec documents.
- Clarified that the baseline freezes framework seams and ownership boundaries, while some adapters and orchestration paths remain scaffold-level implementations.
- Replaced prebuilt database URL configuration with atomic database fields and moved runtime URL assembly into the container.
- Standardized the repository contract on `TAILMATE_PROJECT_ID`, `TAILMATE_LOCATION`, and `TAILMATE_NETWORK_ATTACHMENT`, while keeping Google-managed project and location variables as compatibility fallbacks.
- Restored the documented `LOCAL` storage contract to the active implementation: local runs use the filesystem-backed blob-store adapter, while `CLOUD` runs use Google Cloud Storage.
- Switched Agent Engine dependency export to `uv.lock` and pinned the deployment runtime contract to Python `3.11`.

### [Fixed]

- Hardened cloud config validation for secret-backed database passwords, private IP enforcement, and network attachment requirements.
- Blocked startup when `TAILMATE_DB_PASSWORD` still uses the placeholder value and reduced the risk of secret leakage through config repr/logging.
- Removed the temporary `probe/ping` Agent Engine infrastructure probe path and its dedicated deployment packaging assets.
- Removed the legacy ADK prototype entrypoint and package that still depended on stale variables such as `GCP_PROJECT_ID` and `TAILMATE_VPC_CONNECTOR`.
- Stopped requiring `TAILMATE_MEDIA_BUCKET` in `LOCAL` mode so configuration validation matches the runtime container wiring.
- Ignored generated `.agent_engine_build/` bundles so local deployment artifacts do not pollute the repository status.

### [Breaking Changes]

- Removed the temporary `deploy-tailmate-probe` command and the associated probe-only deployment modules.
- Replaced the previous `ALLOYDB_*`, `*_DATABASE_URL`, and `TAILMATE_VPC_CONNECTOR` contract surfaces with the current `TAILMATE_*` runtime and deployment settings.

## v0.1.0 - 2026-03-24

### [Added]

- Established the frozen hexagonal repository baseline for Tailmate on Vertex AI Agent Engine.
- Added the official development guide, repository blueprint, and documentation policy.
- Added a local environment template and quick-start setup guidance.

### [Changed]

- Promoted the current repository skeleton to the official `v0.1.0` engineering baseline.
- Defined semantic versioning, vertical-slice delivery, three-dimensional agent iteration, and staged rollout rules in the documentation set.

### [Fixed]

- Removed local ADK runtime state from version control and ignored future `.adk/` and `*.db` artifacts.

### [Breaking Changes]

- None. This baseline establishes the first official versioned contract surface.
