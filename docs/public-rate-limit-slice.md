# Public Rate Limit Slice

Version: `v0.13.0`
Status: Per-user sliding-window rate limiting for the public `/v1/agent/query` ingress

This spec records the first public-ingress rate-limit slice for Tailmate.
It exists to keep the request-throttling contract, storage choice, and validation path versioned alongside the implementation.

## Business Goal

`POST /v1/agent/query` is the main public entrypoint and already requires Firebase authentication.
That is not sufficient to protect Tailmate from cost spikes or service degradation caused by one authenticated user sending high-volume concurrent traffic.

Tailmate therefore needs a per-user sliding-window rate limiter on the public query route.

## Slice Mapping

### Contract

- `src/tailmate/adapters/db_gateway/config.py`
  Defines the public rate-limit settings with defaults of `30` requests per `60` seconds.
- `src/tailmate/adapters/database/models.py`
  Adds the canonical `public_query_rate_limit_events` table metadata for persisted sliding-window tracking.

### Adapter

- `src/tailmate/adapters/db_gateway/rate_limiter.py`
  Owns the sliding-window limiter contract plus both the database-backed production implementation and the in-memory test/local implementation.
- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Applies the limiter only to `POST /v1/agent/query`, returns `429` with `Retry-After` plus rate-limit headers, and logs rate-limit denials with the authenticated user id.
- `src/tailmate/adapters/database/migrations/versions/c1e9f6a3b2d4_add_public_query_rate_limit_events.py`
  Creates the persisted rate-limit event table and supporting lookup index.

### Skill

- No new runtime skill is introduced in this slice.

### Orchestration

- No agent-graph routing changes are required.
- Public ingress protection remains at the gateway boundary before the request is sent to Agent Engine.

## Public Limit Contract

Target route:

- `POST /v1/agent/query`

Scope:

- one Firebase-authenticated `user_id`

Default limit:

- `30` requests per `60` seconds per user

Over-limit behavior:

- returns HTTP `429`
- returns `Retry-After`
- returns `X-RateLimit-Limit`
- returns `X-RateLimit-Remaining`
- returns `X-RateLimit-Window-Seconds`

## Storage Strategy

Tailmate uses a database-backed sliding window for the default public gateway deployment.
That keeps rate limiting effective across multiple Cloud Run instances without introducing Redis before it is otherwise needed in the platform.

The repository also keeps an in-memory limiter for tests and injected local fallbacks.

## Validation Path

### Local Sandbox

1. Apply the schema with `uv run alembic upgrade head`.
2. Run `uv run python -m compileall src`.
3. Run `uv run python -m pytest tests/unit/test_gateway_app.py tests/integration/test_public_rate_limiter.py`.
4. Confirm the second request is rejected with `429` when the configured in-memory test limit is exceeded.
5. If the local public gateway starts before the migration is applied, expect one warning log and an in-memory fallback for that process only; apply the Alembic head and restart the gateway to restore the database-backed limiter.

### Cloud Validation

1. Deploy the public gateway with the new migration applied.
2. Confirm a single user receives `429` after crossing the configured threshold.
3. Confirm a different authenticated user is unaffected by the first user's window.
4. Confirm `Retry-After` and the rate-limit headers are present on the `429` response.

## Release Framing

### Cognition

- Tailmate now treats public-ingress abuse control as part of the published `/v1/` contract instead of a deployment-only concern.

### Action

- The public DB gateway now enforces a per-user sliding-window limit before invoking Agent Engine.
- The limiter is safe for multi-instance deployments because it persists request timestamps in PostgreSQL by default.

### Memory

- The public ingress now records recent query events in a dedicated table so the active rate-limit window can be reconstructed consistently across instances.
