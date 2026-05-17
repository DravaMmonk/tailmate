# Tailmate Development Guide

Version: `v0.5.1`
Status: Official pre-1.0 engineering guide for the current repository skeleton

This document is the binding engineering standard for Tailmate.
It confirms the current repository skeleton as the approved development baseline and defines how business features must be added without breaking the existing hexagonal structure.

Primary platform reference:

- [Develop a custom agent](https://docs.cloud.google.com/agent-builder/agent-engine/develop/custom)

Related platform references:

- [Vertex AI Agent Engine overview](https://docs.cloud.google.com/agent-builder/agent-engine/overview)
- [Sessions overview](https://docs.cloud.google.com/agent-builder/agent-engine/sessions/overview)

## 1. Baseline Confirmation

The current repository is intentionally a skeleton.
It contains the final architectural boundaries, deployment entrypoints, runtime contracts, and extension seams, but it does not yet contain full business implementations.

This is the expected state for the current pre-1.0 development baseline.

Tailmate is still in active development.
`1.0.0` is reserved for the first stable public contract, not for the current internal milestone structure.

From this point forward:

- the directory structure in `docs/repository-blueprint.md` is the canonical layout
- the current layering must be preserved
- new business work must fill the approved extension points instead of creating parallel architecture
- changes to frozen areas require explicit architecture review before implementation

Baseline interpretation rule:

- "baseline" means the framework contract is frozen and reviewable
- it does not mean every adapter or business path is feature-complete
- when an implementation is still scaffold-level, documentation must say so explicitly instead of describing it as production-ready

## 2. Working Language Policy

The working language for this repository and its GitHub collaboration surface is English.

Mandatory rules:

- all source code must be written in English
- all code comments must be written in English
- all Markdown documents and internal technical notes committed to the repository must be written in English
- all commit messages must be written in English
- all identifiers such as class names, function names, field names, enum values, and migration names must be written in English
- all Pull Request titles, issue descriptions, release notes, and review notes must be written in English

Allowed exception:

- localized user-facing strings, multilingual extraction dictionaries, and language-specific test fixtures may include non-English text when they are intentionally validating or shipping localization behavior; the surrounding code, comments, and documentation must still be written in English

Forbidden patterns:

- mixed-language code comments
- non-English business terminology inside committed source files
- creating duplicated English and non-English copies of the same technical document inside the repository

## 3. Documentation Version Control Policy

Tailmate treats documentation as code.
Repository documentation is part of the product contract and must be version-controlled in Git alongside the implementation it describes.

The following documents are specs and must remain in the repository:

- `README.md`
- `CHANGELOG.md`
- `docs/*.md`
- `deployment/**/*.md`
- `infra/**/*.md`
- `tests/**/*.md`
- `src/tailmate/adapters/database/migrations/**/*.md`

Mandatory rules:

- any Pull Request that changes architecture, repository ownership, runtime lifecycle, deployment flow, testing scope, or migration process must update the relevant spec documents in the same Pull Request
- spec documents must be reviewed with the same rigor as code changes
- documentation updates must be atomic with the code changes they describe
- historical Git tags define the authoritative document set for that code version
- deleting a spec requires explicit replacement or architecture approval

Review gate:

- if code changes alter contracts, layer ownership, or developer workflow and no relevant spec changes are included, the Pull Request must be blocked

## 4. Non-Negotiable Requirements

| Dimension | Mandatory Requirement |
| --- | --- |
| Deployment environment | Must deploy to Vertex AI Agent Engine (Reasoning Engine). |
| Network connectivity | Must use a Private Service Connect network attachment for private connectivity to internal services and databases. |
| State storage (SSOT) | Conversation context must be persisted in the database. In-memory agent state is never the source of truth. |
| Code structure | Must preserve the split `Agent Class -> Graph Orchestrator -> Independent Tools`. |
| Extensibility | Any new business capability must enter the system as a registered skill. |
| Serialization safety | Constructor state must remain serializable and pickle-safe for Agent Engine deployment. |
| Runtime modes | Local development must run through a standardized `LOCAL` sandbox and deployment must force `CLOUD` mode. |

Current baseline evidence:

- `src/tailmate/entrypoints/local_dev.py` enforces `LOCAL`, loads `.env`, checks the database tunnel, validates ADC only when the configured extraction strategy requires live Gemini access, and now relies on the checked-in global Gemini endpoint defaults for local extraction
- `src/tailmate/entrypoints/deploy.py` enforces `CLOUD`
- `src/tailmate/bootstrap/config.py` accepts atomic database credentials instead of prebuilt connection URLs and rejects missing cloud-only settings in `CLOUD` mode
- `src/tailmate/bootstrap/container.py` resolves blob storage by environment, using a local filesystem adapter in `LOCAL` and GCS in `CLOUD`
- `src/tailmate/adapters/database/conversation_store.py` persists session state through SQL and keeps database ownership behind the session-store port
- `src/tailmate/agent_runtime/current_context.py` provides a request-scoped metadata bridge for values such as `dog_id`
- `deployment/agent_engine/requirements.txt` is exported from `uv.lock` to keep deployment dependencies aligned with the resolved local runtime contract

## 5. GitHub Flow

Tailmate uses a lightweight GitHub Flow that fits a small pre-1.0 team.
The `main` branch must remain deployable at all times.

### 5.1 Branch Strategy

- `main`
  Protected integration branch. Direct pushes are forbidden.
- `feature/{feature-name}`
  Feature development branch created from `main`.
- `fix/{bug-name}`
  Bug-fix branch created from `main`.
- `docs/{topic}`
  Documentation or process-change branch created from `main`.
- `chore/{topic}`
  Maintenance or tooling branch created from `main`.

Rules:

- branch names must be short, English, and descriptive
- branches should be short-lived and merged back into `main` through Pull Requests

### 5.2 Delivery Loop

1. Branch from `main` using the naming rules above.
2. Open a Draft Pull Request early for multi-day, risky, or architecture-affecting work; otherwise open a review-ready Pull Request before merge.
3. Implement the change within the approved extension points in this guide.
4. Update specs and `CHANGELOG.md` when the change affects contracts, workflow, or versioned behavior.
5. Complete the local verification and checklist in this document.
6. Merge through `Squash and merge` after self-review and approval.

### 5.3 Pull Request Rules

- direct commits to `main` are forbidden
- every branch that lands in `main` must merge through a Pull Request
- substantial feature and bug-fix Pull Requests should link a GitHub Issue or equivalent scope record
- Pull Request titles, descriptions, and review notes must be written in English
- unreviewed schema changes must not be merged
- architecture-affecting changes must call out the impacted frozen or non-frozen layer explicitly
- missing required updates to spec documents must block review completion

## 6. Pre-1.0 Product Iteration Policy

Product iteration in Tailmate must follow controlled vertical slices.
Once the baseline architecture is frozen, product progress is measured by complete business increments instead of horizontal layer-only work.

### 6.1 Semantic Versioning

Tailmate must use `0.MINOR.PATCH` until the first stable public release.

- `MAJOR`
  Reserved for the future `1.0.0` decision and post-GA breaking lines.
- `MINOR`
  The default iteration level for Tailmate product work before `1.0.0`.
  Use `0.MINOR.0` for a feature slice, meaningful workflow capability, or externally visible contract expansion.
- `PATCH`
  Use `0.MINOR.PATCH` for a backward-compatible bug fix, reliability fix, prompt/tool correction, or non-breaking documentation or operations update on the active minor line.

Rules:

- tags must use full semantic versions such as `v0.5.1`
- pre-release candidates may use full semantic versions with `-alpha.N`, `-beta.N`, or `-rc.N`
- vague version labels such as `v0` or `v0.5` are forbidden
- breaking changes are still allowed before `1.0.0`, but they must be called out explicitly in the changelog and Pull Request description
- `1.0.0` requires an explicit decision that the product and operator contracts are stable enough for external consumers

### 6.2 Vertical Slice Delivery

Each feature iteration must ship as one complete business slice.
Do not stage work as "all database changes first" or "all skill work later."

Every feature slice must cover:

1. `Contract`
   Define or update the typed data exchange contract.
2. `Adapter`
   Prepare the required persistence, storage, or integration boundary.
3. `Skill`
   Implement the business action surface and tool behavior.
4. `Orchestration`
   Mount, route, and instruct the agent to use the new capability correctly.

Review rule:

- a minor release is incomplete if any of these four slice elements is missing for the intended business outcome

### 6.3 Three-Dimensional Agent Iteration

Every minor release must explicitly describe its changes across these three agent dimensions:

- `Cognition`
  Prompt precision, system boundaries, model choice, and reasoning policy.
- `Action`
  Skill coverage, tool reliability, adapter behavior, and side-effect safety.
- `Memory`
  Retrieval quality, persistence shape, state reconstruction, and historical context usage.

Release planning rule:

- each minor release must state what improved in cognition, action, and memory, even when one dimension has no material change

### 6.4 Changelog Policy

Tailmate must maintain a repository-level `CHANGELOG.md`.

Each release entry must use these sections when applicable:

- `[Added]`
  New skills, tools, or user-facing capabilities.
- `[Changed]`
  Behavior updates, orchestration tuning, prompt changes, or operational refinements.
- `[Fixed]`
  Bug fixes. Reference the relevant GitHub Issue when one exists.
- `[Breaking Changes]`
  Any change that breaks an existing contract, schema expectation, or integration assumption.

Hard rules:

- "fixed some bugs" style entries are forbidden
- breaking changes must call out the impacted contract or compatibility boundary explicitly
- changelog entries and GitHub release notes must be written in English

### 6.5 Deployment Rollout Policy

Agent Engine releases must use staged rollout discipline.

Required sequence:

1. deploy the new version to staging or an inactive release target
2. run the regression prompt and tool validation set
3. confirm no response-quality or execution regressions
4. move the production alias or traffic pointer only after validation passes

Release rule:

- production cutover must not be the first execution of a newly built agent version

## 7. Frozen Architecture Zones

The following areas are frozen in the current development baseline.
Do not modify them unless the change has been explicitly approved as an architecture change.

| Path | Status | Responsibility | Why It Is Frozen |
| --- | --- | --- | --- |
| `src/tailmate/agent_runtime/` | Frozen | Orchestration core, runtime models, and ports | It is the central control plane and contract surface for all skills. Breaking it destabilizes the entire agent. |
| `src/tailmate/bootstrap/` | Frozen | Dependency injection and runtime assembly | The lazy factory and wiring rules protect deployment serialization and startup safety. |
| `src/tailmate/agents/root/agent.py` | Frozen | Agent Engine lifecycle entrypoint | It is the deployable root agent contract for the cloud runtime. |
| `src/tailmate/adapters/vertex_agent_engine/` | Frozen | Vertex AI Agent Engine integration boundary | It owns cloud-runtime-specific wiring such as session mapping and observability. |

Allowed work near frozen zones:

- add new contract types consumed by the frozen layers
- register new skills through existing extension points
- update prompts in `src/tailmate/agents/root/prompts.py`
- add new adapters or business modules outside the frozen directories when they respect existing ports and ownership boundaries

Frozen means:

- preserve public responsibilities, lifecycle ownership, and dependency direction
- preserve the deployable `RootAgent -> GraphOrchestrator -> ports/adapters` split
- preserve runtime mode semantics and constructor serialization safety
- do not rewrite these zones to host feature logic just because they are currently thin

Frozen does not mean:

- every class in these paths is already feature-complete
- placeholder implementations may never be filled in behind the same contracts

## 8. Agent Engine Design Constraints

The official custom agent model imposes these binding rules:

- the deployable unit is a Python class
- `__init__()` is for configuration parameters only
- constructor state must remain serializable and pickle-safe
- heavy initialization such as service clients, database connections, and tracing must happen in `set_up()`
- request handling must be exposed through typed operations such as `query()` and optionally `stream_query()`
- additional callable operations must be registered explicitly when needed
- operation input and output must be JSON-serializable and explicitly typed

Forbidden in `__init__()`:

- opening database connections
- creating long-lived non-serializable SDK clients
- loading mutable runtime state
- performing network calls

## 8.1 Runtime Mode Contract

Tailmate distinguishes between two runtime modes:

- `LOCAL`
  Loads environment variables from `.env`, connects to Cloud SQL through the developer-managed Auth Proxy, runs pre-flight checks before startup, and resolves logical media paths through the local filesystem adapter.
- `CLOUD`
  Targets Vertex AI Agent Engine, uses managed cloud adapters such as Google Cloud Storage, and can reach Cloud SQL either through a private IP path or through the Cloud Run gateway.

Rules:

- mode selection must be explicit through `TAILMATE_ENV`
- `LOCAL` mode must not require cloud-only settings such as network attachment names or media buckets
- `CLOUD` mode must reject startup when cloud-only settings are missing
- `TAILMATE_PROJECT_ID` and `TAILMATE_LOCATION` are the canonical project and region contract; `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `CLOUD_ML_REGION` are compatibility fallbacks only
- deployment code must force `TAILMATE_ENV=CLOUD` before building the deployable agent
- direct database connection strings must be assembled inside the runtime from atomic fields instead of being supplied as a single environment variable
- deployment dependency bundles must be exported from the lockfile instead of a hand-maintained side list
- the deployment Python runtime must be pinned explicitly to `3.11`

Atomic database contract:

- `TAILMATE_DB_USER`
  Required in `LOCAL` and in `CLOUD` direct-database mode.
- `TAILMATE_DB_PASSWORD`
  Required in `LOCAL` and in `CLOUD` direct-database mode.
- `TAILMATE_DB_IP`
  Required in `LOCAL` and in `CLOUD` direct-database mode.
  This must be a Cloud SQL private IP reachable from the configured network attachment.
- `TAILMATE_DB_NAME`
  Optional. Defaults to `tailmate`.
- `TAILMATE_DB_GATEWAY_URL`
  Optional in `CLOUD`. When set, the runtime persists session state through the Cloud Run gateway and deployment omits PSC attachment settings.
- `TAILMATE_NETWORK_ATTACHMENT`
  Required only in `CLOUD` direct-database mode and must match `projects/{project}/regions/{region}/networkAttachments/{name}`.
  This repository standardizes on the full resource path even when the attachment lives in the same project.
- `TAILMATE_MEDIA_BUCKET`
  Required only in `CLOUD`.
- `TAILMATE_LOCAL_MEDIA_ROOT`
  Optional in `LOCAL`. Defaults to `/data/tailmate`.
- `TAILMATE_DNS_PEERING_DOMAIN`
  Optional in `CLOUD`. When set, it must be the DNS suffix of the private Cloud DNS zone that Vertex AI should peer with.
- `TAILMATE_DNS_PEERING_TARGET_PROJECT`
  Optional in `CLOUD`. When DNS peering is configured, this must be the project that hosts the target VPC network.
- `TAILMATE_DNS_PEERING_TARGET_NETWORK`
  Optional in `CLOUD`. When DNS peering is configured, this must be the target VPC network name.

Database host routing rule:

- `LOCAL` must ignore `TAILMATE_DB_IP` for host routing and connect through the local proxy host and port
- `CLOUD` direct mode must connect to `TAILMATE_DB_IP:5432`
- `CLOUD` gateway mode must call `TAILMATE_DB_GATEWAY_URL` over HTTPS with an ID token

Private-network prerequisites:

- the PSC network attachment subnet must use routable RFC 1918 address space
- Google recommends a `/28` subnet for Vertex AI PSC interfaces
- the Vertex AI service agent must have `roles/compute.networkAdmin` in the network attachment project
- in Shared VPC topologies, the Vertex AI service agent must also have `roles/compute.networkUser` in the host project
- regional baseline deployments that connect directly to a private endpoint IP do not require DNS peering
- when private Cloud DNS peering is used, the Vertex AI service agent must have `roles/dns.peer`
- `TAILMATE_DNS_PEERING_DOMAIN`, `TAILMATE_DNS_PEERING_TARGET_PROJECT`, and `TAILMATE_DNS_PEERING_TARGET_NETWORK` must always be set together

## 9. Required Architecture

Every shipped feature must preserve this layering:

1. `Agent Class`
   Receives configuration only and owns lifecycle methods such as `set_up()` and `query()`.
2. `Graph Orchestrator`
   Owns reasoning flow, routing, guardrails, state transitions, and skill invocation.
3. `Independent Tools`
   Encapsulate side effects and integrations behind narrow, testable interfaces.

Hard rules:

- no tool may decide orchestration flow
- no orchestrator may inline infrastructure bootstrapping
- no entrypoint may bypass the deployable agent lifecycle
- conversation state must always be reconstructable from persistent storage
- if cached state and database state diverge, the database wins

Current development baseline note:

- this rule defines the required architecture boundary
- the present repository skeleton has the schema, store interface, and ownership seam in place, and the concrete conversation store now performs real row-level persistence

## 10. Feature Implementation Path

When implementing a new business feature, add it through the approved layers in the following order.

Example feature: dog step analysis.

### Step 1. Define Contracts

Location:

- `src/tailmate/contracts/types.py`

Required work:

- add typed request and response models for the feature
- keep payloads JSON-serializable
- treat this module as the single source of truth for cross-layer data exchange

Goal:

- the agent, orchestrator, skills, and adapters all speak the same typed language

### Step 2. Add Persistence

Location:

- `src/tailmate/adapters/database/models.py`
- `src/tailmate/adapters/database/migrations/`

Required work:

1. add or update the SQLAlchemy models
2. create an Alembic revision with `alembic revision --autogenerate`
3. review the generated migration manually before applying it
4. apply the migration to the target environment through the approved tunnel flow

Hard rules:

- schema changes must be script-based and checked in
- runtime code must not create production tables ad hoc
- business data must remain reachable through approved ports and adapters

### Step 3. Implement the Skill

Location:

- `src/tailmate/skills/`

Required work:

1. add a new skill module such as `step_analysis_skill.py`
2. inherit from the shared base skill contract
3. expose focused tool functions with stable typed input and output
4. keep side effects inside tools or adapters, not in prompt-only logic
5. register the skill in `src/tailmate/skills/registry.py`

Preferred implementation pattern:

- place each skill in `src/tailmate/skills/{skill_name}/`
- export `SKILL_DEFINITION` from `manifest.py` or `__init__.py`
- declare the input contract path, output contract path, and adapter dependency ids in the manifest
- let the container auto-discover the skill instead of hardcoding it into the registry
- expose feature rollout state through `default_enabled`, `TAILMATE_ENABLED_SKILLS`, and `TAILMATE_DISABLED_SKILLS` instead of deleting code on the first rollback

Developer scaffold:

- generate the initial vertical slice skeleton with `tailmate new-skill <skill_name>`
- the scaffold must create at least contract, adapter stub, skill package, contract test, integration test, unit test, and a controlled slice document

Hard rules:

- skills must not bypass ports and import infrastructure directly unless the adapter boundary explicitly allows it
- skills must remain attachable and removable through registration
- feature logic must not be hardcoded into the root agent body

### Step 4. Update Prompts and Orchestration

Location:

- `src/tailmate/agents/root/prompts.py`

Required work:

- teach the root agent when to use the new skill
- describe the capability in operational English
- keep prompt instructions aligned with the actual registered feature surface

Use this layer for behavior shaping, not for embedding business side effects.

## 11. Testing and Quality Gates

### 11.1 Local Sandbox Flow

Every feature must be validated locally before review.

1. Start the database proxy:

   ```bash
   ./scripts/start_cloudsql_proxy.sh
   ```

   The helper must use `cloud-sql-proxy` and target the configured `CLOUDSQL_INSTANCE_CONNECTION_NAME`.

2. Run the local bootstrap:

   ```bash
   uv run python src/tailmate/entrypoints/local_dev.py
   ```

3. Verify the feature path end to end.

Minimum expected checks:

- the database receives the expected writes
- the active blob-store adapter receives the expected objects when storage is part of the feature
- the agent response follows the intended logic

### 11.2 Cloud Validation Flow

Every cloud-bound feature must also be validated against the deployed runtime path.

1. Deploy the Cloud Run gateway revision first when the feature changes gateway routes, media processing, or gateway-side environment variables.
2. Confirm the gateway runtime service account can read its secrets and write to the configured media bucket.
3. Confirm Alembic head has been applied to the exact database endpoint used by the deployed runtime path.
4. Deploy Agent Engine with an explicit runtime service account when gateway mode is enabled.
5. Run `deployment/agent_engine/smoke_test.py` with the required project, location, and resource-name variables.
6. Read back the persisted database rows and stored media objects for the feature-specific acceptance checks.

Operational note:

- local proxy validation and cloud gateway validation may hit different private database endpoints; schema state must be verified on both paths when they differ

### 11.3 Pickle Safety Audit

Every time `__init__()` changes, ask these questions:

- did I introduce a non-serializable object into constructor state
- if I need a database engine, file handle, or SDK client, did I keep it behind lazy runtime setup or a factory method

If the answer is unclear, the change is not ready to merge.

### 11.4 Mandatory Static Validation

Run these commands before opening a merge-ready PR:

```bash
python -m compileall src
pytest tests/unit
```

Add integration or contract tests when the feature changes persistence, runtime wiring, or exposed schemas.

## 12. Pull Request Checklist

A PR is not ready until every answer is yes.

- [ ] Did the feature define or update shared payloads in `src/tailmate/contracts/types.py` when cross-layer data changed?
- [ ] Does the feature reach infrastructure through ports and adapters instead of importing low-level implementations into business flow?
- [ ] Does `RootAgent.__init__()` remain free of I/O objects and runtime state?
- [ ] Are all schema changes represented by Alembic migrations?
- [ ] Do the critical feature steps emit traceable logs or observability events?
- [ ] Does the feature preserve `Agent Class -> Graph Orchestrator -> Independent Tools`?
- [ ] Is all committed code, documentation, and GitHub collaboration content in English, except for explicit localization fixtures?
- [ ] Were all impacted specs updated in the same Pull Request?
- [ ] Does the changelog entry classify the change correctly as `0.MINOR.0`, `0.MINOR.PATCH`, or a tagged pre-release?
- [ ] If the change is breaking during pre-1.0 development, is that called out explicitly?
- [ ] For a minor release, does the delivered work form one complete vertical slice?

## 13. Review Standard

Changes must be rejected if they do any of the following:

- introduce a parallel architecture outside the approved blueprint
- place business logic inside frozen runtime infrastructure
- bypass the skill registry for new capabilities
- store the conversation source of truth in process memory
- add database schema changes without migrations
- introduce non-English committed technical content
- omit required updates to specs when code contracts or workflow changed
- classify a release ambiguously or skip the changelog for a versioned change

This document and `docs/repository-blueprint.md` together define the official Tailmate pre-1.0 engineering standard.
