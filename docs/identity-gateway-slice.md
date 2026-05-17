# Identity Gateway Slice

Version: `v0.11.0`
Status: Firebase-backed public ingress with versioned `/v1/` public routes, privacy export/delete, master accounts, platform connections, and owner-isolated dog/media access

This spec records the identity and ownership-isolation slice for Tailmate.
It exists to keep the public ingress contract, internal trust boundary, schema changes, and release framing versioned alongside the implementation.

## Business Goal

Tailmate needs a public agent ingress that can accept end-user requests without exposing the internal database or media APIs directly.
Those public requests must resolve to a bound Tailmate user, and every dog-profile or media mutation must stay scoped to that owner unless a later explicit sharing model is introduced.

## Slice Mapping

### Contract

- `src/tailmate/contracts/constants.py`
  Defines the versioned public route constants, the public web platform constant, the supported account-connection platforms, and the trusted internal `X-Tailmate-User-Id` transport header.
- `src/tailmate/contracts/errors.py`
  Adds explicit `AuthenticationError`, `AuthorizationError`, `NotFoundError`, and `ConflictError` types so the gateway can return stable account-lifecycle outcomes.
- `src/tailmate/contracts/types.py`
  Adds the `PublicAgentQueryInput`, `PlatformConnectionInput`, and `BridgeQueryInput` contracts plus normalization for the public registration, activation, connection, and bridge-query routes.
- `src/tailmate/contracts/dog_profile.py`
  Tightens dog-profile creation to require `user_id` and dog-profile enrichment to require `requesting_user_id`.
- `src/tailmate/agent_runtime/current_context.py`
  Extends request-scoped runtime context with `user_id` so downstream adapters can enforce ownership without widening unrelated tool signatures.

### Adapter

- `src/tailmate/agent_runtime/ports/dog_profile_db_adapter.py`
  Declares owner-scoped profile loading through `load_profile(..., requesting_user_id=...)`.
- `src/tailmate/adapters/db_gateway/identity.py`
  Resolves master accounts from `users`, resolves platform identities through `user_platform_connections`, manages web registration plus account activation, and builds the internal session namespace `{user_id}__{platform}__{external_conversation_id}`.
- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Registers two route sets from the same Flask module: the public Firebase-protected `/v1/users/register`, `/v1/users/activate`, `/v1/users/<user_id>/export`, `/v1/users/<user_id>`, `/v1/users/connections/<platform>`, and `/v1/agent/query` ingress routes plus the IAM-protected `/bridge/query` internal route and the existing internal DB/media APIs.
- `src/tailmate/adapters/db_gateway/client.py`
  Automatically forwards the trusted internal `X-Tailmate-User-Id` header on owner-scoped dog-profile and media gateway calls.
- `src/tailmate/adapters/db_gateway/dog_profile.py`
  Keeps gateway-mode dog-profile reads and enrich calls owner-scoped through the trusted user id.
- `src/tailmate/adapters/dog_profile/db_adapter.py`
  Enforces owner checks before returning or mutating a dog profile through the direct SQL path.
- `src/tailmate/adapters/media/sanitized_media_store.py`
  Verifies the current request user owns the referenced dog before local media sanitization writes any blob or media row.
- `src/tailmate/adapters/database/models.py`
  Keeps `users` as the master account table, adds `user_platform_connections`, and preserves the `dog_profiles.user_id -> users.user_id` ownership boundary.
- `src/tailmate/adapters/database/migrations/versions/0c2b5a17d9f1_add_users_table_and_enforce_dog_.py`
  Creates the original owner-bound `users` table and hardens dog-profile ownership at the schema level.
- `src/tailmate/adapters/database/migrations/versions/d4a8f8c7e2b1_split_master_accounts_from_platform_connections.py`
  Backfills `user_platform_connections` from the legacy `users.platform/platform_user_id` columns, then removes those single-platform fields from `users`.

Schema note:

- This slice changes the database schema and therefore requires the checked-in Alembic migration before owner-scoped flows can work.

### Skill

- No new business skill is introduced in this slice.
- `src/tailmate/skills/dog_profile/skill.py`
  Reuses the existing tools while honoring the tightened owner-scoped input contracts.
- `src/tailmate/skills/strip_metadata/skill.py`
  Continues to operate through the existing skill boundary, now relying on owner-scoped media adapters underneath.

### Orchestration

- `src/tailmate/agent_runtime/services/graph_orchestrator.py`
  Requires a verified `metadata["user_id"]` before it attempts implicit dog-profile create or enrich flows.
- `src/tailmate/agents/root/agent.py`
  Threads the verified user id into the request-scoped runtime context bridge.
- `src/tailmate/entrypoints/vertex_test_ui.py`
  Accepts an optional trusted test user id so staged operator validation can exercise owner-scoped flows without the public Firebase ingress.
- `deployment/agent_engine/smoke_test.py`
  Accepts an optional trusted smoke-test user id for the same owner-scoped validation path.
- `docs/adr-0002-public-api-versioning-strategy.md`
  Records the path-versioning policy for external callers and the explicit non-versioned boundary for private IAM-only routes.
- `docs/adr-0003-hard-delete-user-privacy-requests.md`
  Records the accepted hard-delete sequencing for public privacy requests across PostgreSQL, GCS, and Firebase.

## Versioning Boundary

- Public caller-facing Firebase ingress routes are path-versioned and now start at `/v1/`.
- Internal IAM-only routes such as `/bridge/*`, `/sessions/*`, `/dog-profiles/*`, `/media/*`, and `/knowledge/*` remain unversioned in this slice because they are private operational contracts, not externally published client APIs.
- Future public breaking changes must land on a new `/vN/` prefix instead of mutating `/v1/` in place.

## Validation Path

### Local Sandbox

1. Start the Cloud SQL Auth Proxy with `./scripts/start_cloudsql_proxy.sh`.
2. Apply the schema with `uv run alembic upgrade head`.
3. Run `uv run python -m compileall src tests tailmate-db-gateway/main.py`.
4. Run `uv run python -m pytest tests/unit`.
5. Run `uv run python -m pytest tests/integration tests/contract`.
6. Validate the account lifecycle:
   - `POST /v1/users/register` with a Firebase token creates a `pending` master account plus an `active` web connection
   - `POST /v1/users/activate` with the same Firebase token transitions the master account to `active`
   - `GET /v1/users/<user_id>/export` returns the authenticated caller's full owner-scoped data snapshot
   - `DELETE /v1/users/<user_id>` hard-deletes the authenticated caller's account data and external assets
   - `POST /v1/users/connections/telegram` with the active Firebase token creates a `pending_verification` Telegram connection
   - `DELETE /v1/users/connections/telegram` marks that connection as `disconnected`
7. Validate the owner-scoped local path with a bound active user id:
   - `uv run tailmate local-demo --message "My dog is Peanut." --dog-id demo-dog --user-id <bound-user-id>`
   - `uv run tailmate local-demo --file /absolute/path/to/sample.jpg --dog-id demo-dog --user-id <bound-user-id>`
8. Confirm that the same dog or media request fails with `403` when a different trusted user id is used.

### Cloud Validation

1. Apply the `users` plus `user_platform_connections` migrations to the database used by the gateway and agent runtime.
2. Deploy the shared gateway codebase as an internal IAM-only service with `TAILMATE_GATEWAY_ENABLE_INTERNAL_DB=true` and `TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY=false`.
3. Deploy the same gateway codebase as a separate public ingress service with `TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY=true`, `TAILMATE_GATEWAY_ENABLE_INTERNAL_DB=false`, and the Firebase plus Agent Engine env vars.
4. Verify the public lifecycle by calling:
   - `POST /v1/users/register` with a Firebase ID token for a new caller
   - `POST /v1/users/activate` with the same Firebase ID token
   - `GET /v1/users/<user_id>/export` with the same Firebase ID token
   - `DELETE /v1/users/<user_id>` with the same Firebase ID token against a disposable validation user
   - `POST /v1/users/connections/telegram` with the now-active Firebase ID token
5. Verify the internal bridge route by calling `POST /bridge/query` from an IAM-allowed bridge service with an active non-web platform identity.
6. Verify the public query route by calling `POST /v1/agent/query` with a Firebase ID token for a bound `active` user whose web connection is also `active`.
7. Verify the staged internal route by running the Vertex test UI or `deployment/agent_engine/smoke_test.py` with a trusted test `user_id`.
8. Confirm that:
   - a bound active user can create, enrich, and upload media for their own dog profile
   - an unbound or non-active user is rejected with `403`
   - a disconnected platform identity is rejected with `403`
   - multiple platform identities can resolve to the same `user_id`
   - a bridge service can query as `telegram` without a Firebase token when the internal bridge-query flag is enabled
   - a different trusted user id cannot read, enrich, or upload media against another owner's dog profile

## Deferred Schema

The slice intentionally does not create or consume `profile_access_grants`.
That schema is deferred for a later collaboration/share-access issue and must not appear in runtime code or migrations for `v0.6.0`.

Planned shape:

- `profile_access_grants.dog_id -> dog_profiles.id`
- `profile_access_grants.grantee_user_id -> users.user_id`
- `profile_access_grants.granted_by_user_id -> users.user_id`
- supporting columns such as `scope`, `status`, `created_at`, and `revoked_at`

Planned purpose:

- allow future caregiver, family-member, or clinician access to a profile without transferring profile ownership away from the original owner

## Release Framing

### Cognition

- The runtime now treats verified user identity as a first-class prerequisite for owner-scoped dog-profile and media actions.
- The Cloud Run gateway is no longer a single trust surface: the public `/v1/` Firebase ingress and the internal IAM-only DB/media routes are two deployment modes of the same codebase.

### Action

- Tailmate can now register Firebase-authenticated callers as pending master accounts, activate them, manage per-platform connection lifecycle state, proxy public web queries, and accept IAM-authenticated non-web bridge queries without exposing the internal persistence routes.
- Dog-profile reads, enrichments, and sanitized media writes are now blocked unless the requesting user owns the referenced dog profile.

### Memory

- Master accounts now persist in `users`, per-platform identities now persist in `user_platform_connections`, and internal public-ingress sessions are namespaced by user and channel.
- Owner isolation now exists both in schema shape and in runtime enforcement across direct, gateway, and staged validation paths.
