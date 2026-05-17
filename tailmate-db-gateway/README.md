# Tailmate DB Gateway

This shared Flask module is the approved Cloud Run boundary for Tailmate persistence and public ingress.
The same image must be deployed in two different service modes when both surfaces are needed:

- a public Firebase-protected ingress that exposes versioned account lifecycle routes plus `POST /v1/agent/query`
- an internal IAM-only database and media gateway that exposes the narrow session, bridge-user, bridge-query, dog-profile, and sanitized-upload APIs

Because Cloud Run IAM is service-wide, do not publish both trust models on the same service URL.

## Route Sets

### Public Agent Ingress

Enabled when:

- `TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY=true`
- `TAILMATE_GATEWAY_ENABLE_INTERNAL_DB=false`

Endpoints:

- `GET /entrypoints` when `TAILMATE_GATEWAY_ENABLE_WHATSAPP_ENTRYPOINT=true`
- `POST /v1/users/register`
- `POST /v1/users/activate`
- `GET /v1/users/<user_id>/export`
- `DELETE /v1/users/<user_id>`
- `POST /v1/users/connections/<platform>`
- `DELETE /v1/users/connections/<platform>`
- `POST /v1/agent/query`

Request contract:

- `Authorization: Bearer <Firebase ID token>`
- optional `X-Tailmate-Request-Id: <caller-generated-correlation-id>`; when omitted, the gateway generates one and returns it on the response
- optional standard trace headers `traceparent` and `tracestate`; when present, the gateway continues the incoming trace and propagates the context downstream
- `POST /v1/agent/query` accepts a JSON body with:
  - `message` required
  - `session_id` optional
  - `dog_id` optional
  - `strip_metadata_request` optional
- callers may request SSE by sending `Accept: text/event-stream`
- `POST /v1/users/connections/<platform>` accepts a JSON body with `platform_user_id` and optional `status`
- the privacy export and delete routes do not require a request body
- `GET /entrypoints` proxies the configured WhatsApp adapter entrypoint payload for browser callers on the main web deployment when the feature is enabled

Behavior:

- attaches CORS headers for allowlisted browser origins on `/entrypoints` plus the `/v1/*` public ingress routes
- registers `/entrypoints` only when `TAILMATE_GATEWAY_ENABLE_WHATSAPP_ENTRYPOINT=true`
- verifies the Firebase ID token and extracts the Firebase `uid`
- `POST /v1/users/register` creates a `pending` master account in `users` when needed and ensures an `active` `web` connection row exists in `user_platform_connections`
- `POST /v1/users/activate` transitions the master account from `pending` to `active`
- `GET /v1/users/<user_id>/export` returns the owner-scoped account, platform connection, dog profile, enrichment-log, media, and conversation-session snapshot for the authenticated Firebase user
- `DELETE /v1/users/<user_id>` performs an authenticated hard delete for that same Firebase user, removes owned media objects from blob storage, deletes the Firebase account, and then deletes the persisted owner rows in one database transaction
- `POST /v1/users/connections/<platform>` creates or updates a per-platform connection row
- `DELETE /v1/users/connections/<platform>` marks that connection as `disconnected`
- `POST /v1/agent/query` resolves the caller through `user_platform_connections` joined to `users`
- `POST /v1/agent/query` is rate-limited per authenticated `user_id` with a default sliding window of `30` requests per `60` seconds
- in `LOCAL`, if the `public_query_rate_limit_events` table is missing because the local gateway database has not been migrated yet, the gateway logs a warning once and temporarily falls back to an in-memory limiter until the process restarts
- over-limit public query requests return `429` with `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Window-Seconds`
- streaming query responses emit `query.started`, `query.delta`, and `query.completed` SSE events while preserving the existing JSON response shape for non-streaming callers
- rejects missing, unbound, non-`active`, or disconnected identities with `403`
- injects `metadata["user_id"] = <resolved user_id>`
- injects `metadata["channel"] = "web"` and the active trace context into the downstream agent payload
- rewrites the internal session id to `{user_id}__{platform}__{external_session_id}`
- returns the external caller-visible session id, never the internal namespaced one

Account model:

- `users`
  The master account table keyed by `user_id`, with `status`, `role`, and `created_at`
- `user_platform_connections`
  Per-platform identities keyed by `(user_id, platform)` with unique `(platform, platform_user_id)` and connection lifecycle state

Versioning note:

- Public caller-facing routes are path-versioned under `/v1/`.
- Internal IAM-only routes remain unversioned until Tailmate needs a long-lived compatibility contract for private service-to-service consumers.

### Internal DB And Media Gateway

Enabled when:

- `TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY=false`
- `TAILMATE_GATEWAY_ENABLE_INTERNAL_DB=true`
- `TAILMATE_GATEWAY_ENABLE_BRIDGE_QUERY=true` only when bridge services should be allowed to proxy agent queries through IAM

Endpoints:

- `GET /health`
- `GET /metrics`
- `GET /kb/chunks`
- `POST /kb/chunks`
- `POST /kb/chunks/import`
- `DELETE /kb/chunks/<chunk_id>`
- `POST /bridge/users/ensure`
- `POST /bridge/webhooks/claim`
- `POST /bridge/query`
- `GET /sessions/<session_id>`
- `PUT /sessions/<session_id>`
- `GET /dog-profiles`
- `POST /dog-profiles`
- `GET /dog-profiles/<dog_id>`
- `POST /dog-profiles/<dog_id>/enrich`
- `POST /media/upload`
- `POST /media/strip-metadata`

Health behavior:

- `GET /health` now performs a deep PostgreSQL probe with `SELECT 1`
- it returns structured JSON with `status` plus `checks`
- it returns `503` when the database probe fails
- configure Cloud Run liveness and readiness probes to call `GET /health` on the internal gateway deployment

App-layer caller verification:

- internal routes can require `Authorization: Bearer <Google-signed ID token>`
- optional `X-Tailmate-Request-Id` and `X-Trace-Id` are accepted on internal routes and returned to the caller so bridge services can correlate one request across adapter, gateway, and agent logs
- enable with `TAILMATE_DB_GATEWAY_REQUIRE_AUTH=true`
- configure the expected audience with `TAILMATE_DB_GATEWAY_AUTH_AUDIENCE`
- allowlisted identities in `TAILMATE_DB_GATEWAY_ALLOWED_CALLERS` may perform write methods
- read methods still require a valid bearer token when app-layer auth is enabled

Bridge-query behavior:

- `POST /bridge/users/ensure` is only registered when `TAILMATE_GATEWAY_ENABLE_BRIDGE_QUERY=true`
- it accepts `platform` plus `platform_user_id`
- it rejects `platform='web'` and unsupported platforms
- it provisions a new `active` master account plus `active` platform connection when the phone number or external platform id has not been seen before
- it reactivates non-suspended bridge-managed platform identities when the master account or connection exists but is not currently `active`
- `POST /bridge/webhooks/claim` is only registered when `TAILMATE_GATEWAY_ENABLE_BRIDGE_QUERY=true`
- it accepts `message_id` and atomically inserts the value into `processed_webhook_events`
- it returns `201 {"claimed": true}` for the first delivery and `200 {"claimed": false}` for duplicate deliveries
- `POST /bridge/query` is only registered when `TAILMATE_GATEWAY_ENABLE_BRIDGE_QUERY=true`
- it accepts `platform`, `platform_user_id`, `message`, optional `session_id`, and optional `dog_id`
- it resolves `(platform, platform_user_id)` through `user_platform_connections` joined to `users`
- it rejects `platform='web'`, unsupported platforms, non-`active` master accounts, and non-`active` platform connections
- it rewrites the internal session id to `{user_id}__{platform}__{external_session_id}` and returns only the external session id
- bridge services must call this internal IAM-protected surface; the public Firebase `/v1/agent/query` route remains web-only

Trusted internal transport:

- `X-Tailmate-User-Id` is required on:
  - `POST /dog-profiles`
  - `GET /dog-profiles/<dog_id>`
  - `POST /dog-profiles/<dog_id>/enrich`
  - `POST /media/upload`
  - `POST /media/strip-metadata`

Owner-isolation behavior:

- `POST /dog-profiles` requires `payload.user_id == X-Tailmate-User-Id`
- dog-profile reads and enrichments use the trusted user id as the owner filter
- media uploads verify dog ownership before any blob or database write is performed
- cross-user access attempts return `403`

Session-binding behavior:

- `POST /dog-profiles` binds the supplied `session_id` to the newly created `dog_id`
- `PUT /sessions/<session_id>` preserves an existing bound `dog_id` and rejects rebinding to a different dog
- dog-profile reads, enrichments, and media uploads optionally accept `session_id`; when present, the session must already be bound to the target `dog_id`
- if dog-profile creation succeeds but session binding fails afterward, the gateway deletes the newly created profile before returning the error

## Shared Environment Variables

The gateway now validates its environment through a dedicated `GatewayConfig` settings contract during startup.
Missing required values fail fast with explicit validation errors instead of surfacing later as raw `KeyError` exceptions.

- `DB_HOST`
- `DB_PORT` default `5432`
- `DB_USER`
- `DB_PASSWORD`
- `DB_NAME`
- `DB_CONNECT_TIMEOUT_SECONDS` default `10`
- `TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY`
- `TAILMATE_GATEWAY_ENABLE_INTERNAL_DB`

Additional public-ingress environment:

- `TAILMATE_AGENT_ENGINE_RESOURCE_NAME`
- `TAILMATE_PUBLIC_ALLOWED_ORIGINS` optional comma-delimited browser allowlist for `/entrypoints` and `/v1/*` CORS responses
- `TAILMATE_GATEWAY_ENABLE_WHATSAPP_ENTRYPOINT` optional, defaults to `false`
- `TAILMATE_WHATSAPP_ADAPTER_URL` required when the public ingress should proxy `GET /entrypoints`
- `TAILMATE_WHATSAPP_ADAPTER_TIMEOUT_SECONDS` optional, defaults to `15`
- `TAILMATE_MEDIA_BUCKET` in `CLOUD` mode so privacy deletes can remove stored media objects
- `TAILMATE_PUBLIC_RATE_LIMIT_REQUESTS` optional, defaults to `30`
- `TAILMATE_PUBLIC_RATE_LIMIT_WINDOW_SECONDS` optional, defaults to `60`
- `TAILMATE_FIREBASE_PROJECT_ID` optional, with fallback to `TAILMATE_PROJECT_ID` / `GOOGLE_CLOUD_PROJECT`
- `TAILMATE_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT`
- `TAILMATE_LOCATION` or compatible Google Cloud location env vars

Additional internal DB/media environment:

- `TAILMATE_MEDIA_BUCKET` in `CLOUD` mode
- `TAILMATE_DB_GATEWAY_REQUIRE_AUTH` optional, defaults to enabled outside `LOCAL`
- `TAILMATE_DB_GATEWAY_AUTH_AUDIENCE` when app-layer auth is enabled
- `TAILMATE_DB_GATEWAY_ALLOWED_CALLERS` when app-layer auth is enabled
- `TAILMATE_DB_GATEWAY_MAX_UPLOAD_BYTES` optional, defaults to `52428800`
- `FFMPEG_BINARY` optional, defaults to `ffmpeg`

Compatibility fallbacks:

- `TAILMATE_PROJECT_ID` remains the canonical project contract, with `GOOGLE_CLOUD_PROJECT` accepted as a compatibility fallback
- `TAILMATE_LOCATION` remains the canonical location contract, with `GOOGLE_CLOUD_LOCATION` and `CLOUD_ML_REGION` accepted as compatibility fallbacks
- `TAILMATE_FIREBASE_PROJECT_ID` overrides the Firebase audience when set; otherwise the gateway reuses the resolved project id

Observability note:

- the gateway now emits structured JSON logs for request failures and completions
- the baseline correlation fields are `request_id`, `user_id`, `session_id`, `skill`, `intent`, and `latency_ms`
- the structured log payload now also includes `trace_id` and `span_id` when tracing is active
- `GET /metrics` exposes the shared Prometheus-compatible business metrics surface for internal scraping only
- the gateway also configures OpenTelemetry tracing and continues any incoming W3C trace-context headers for downstream spans
- the local public-query limiter emits `local_public_query_rate_limit_storage_missing` when it has to fall back to in-memory storage because the local database is missing the Alembic-managed rate-limit table

## Media Upload Contract

`POST /media/upload` is the canonical path for sanitized uploads, and `POST /media/strip-metadata` remains as a compatibility alias.
Both expect multipart form data with:

- `dog_id`
- `resource_kind` (`images`, `videos`, or `audio`)
- `session_id` optional
- `file`

Behavior:

- images are reopened and rewritten through Pillow without EXIF metadata
- videos are rewritten through `ffmpeg -map_metadata -1 -c copy`
- audio files are rewritten through `ffmpeg -map_metadata -1 -c copy`, then transcribed through Gemini before the runtime routes the turn as text
- `POST /media/upload` is the only approved cloud ingestion path; direct signed-URL uploads to GCS are intentionally out of scope because metadata must be stripped before any object is stored
- only the sanitized bytes are uploaded to GCS
- the sanitized media reference is written to the `media_assets` table before the request succeeds
- the raw upload is kept only in memory or an ephemeral temp directory and must not be retained after the request completes
- the stored object name is generated from a UUID media id, not the original filename
- the response returns the generated `media_id`, logical path, `media_ref`, and sanitized resource URI
- uploads are rejected when `resource_kind` is not `images`, `videos`, or `audio`
- uploads are rejected when a supplied `session_id` is already bound to a different `dog_id`
- the persisted `media_assets` row records the verified caller identity in `uploaded_by`
- upload size is capped by `TAILMATE_DB_GATEWAY_MAX_UPLOAD_BYTES` (or `TAILMATE_MAX_UPLOAD_BYTES` for backward compatibility)

## Knowledge Base Management Contract

- `GET /kb/chunks`
  Returns a similarity preview for a reviewed KB query using the requested `query`, `locale`, and optional `top_k`.
- `POST /kb/chunks`
  Embeds and upserts one reviewed knowledge chunk.
- `POST /kb/chunks/import`
  Accepts a reviewed chunk batch as JSON or an uploaded CSV/JSON file and bulk imports the reviewed records.
- `DELETE /kb/chunks/<chunk_id>`
  Deletes one reviewed knowledge chunk by id and returns a structured deletion result.

## Dog Profile Contract

- `GET /dog-profiles`
  Returns the owner-scoped dog profile list for the trusted caller so internal runtimes can resolve `active_dog_id` and multi-dog switching without broadening the SQL surface.
- `POST /dog-profiles`
  Creates a new dog profile from at least `name`, `session_id`, and `user_id`, returns `dog_id`, `profile_summary`, and `created_at`, and binds the session to the created dog.
- successful dog-profile creation also emits an `audit_events` row keyed by `trace_id`, `user_id`, `entity_type`, `entity_id`, and `action`
- `GET /dog-profiles/<dog_id>`
  Returns `{ "found": true, "profile": ... }` when the record exists and `{ "found": false, "dog_id": ... }` when it does not.
- `POST /dog-profiles/<dog_id>/enrich`
  Persists a validated extraction result for the existing owner-scoped profile, applies the merged field updates, appends a `raw_note` when present, writes the corresponding `profile_enrichment_log` row, and emits an `audit_events` snapshot for successful mutations.

## Deploy

```bash
PROJECT_ID=tailmate
REGION=us-central1
SERVICE_NAME=tailmate-db-gateway
IMAGE="us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/$SERVICE_NAME:$(date +%Y%m%d-%H%M%S)"
ALEMBIC_DATABASE_URL="postgresql+psycopg2://<user>:<password>@<staging-or-prod-host>:5432/postgres"

# Build from the repository root so the image includes src/tailmate.
gcloud builds submit . \
  --config tailmate-db-gateway/cloudbuild.yaml \
  --substitutions _IMAGE="$IMAGE",_ALEMBIC_DATABASE_URL="$ALEMBIC_DATABASE_URL"

gcloud run deploy $SERVICE_NAME \
  --image="$IMAGE" \
  --region=$REGION \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account=tailmate-agent-sa@tailmate.iam.gserviceaccount.com \
  --network=default \
  --subnet=default \
  --vpc-egress=private-ranges-only \
  --set-env-vars="DB_HOST=<cloudsql-private-ip>,DB_PORT=5432,DB_USER=<db-user>,DB_NAME=postgres,DB_CONNECT_TIMEOUT_SECONDS=10,TAILMATE_MEDIA_BUCKET=<media-bucket>,TAILMATE_GATEWAY_ENABLE_PUBLIC_QUERY=false,TAILMATE_GATEWAY_ENABLE_INTERNAL_DB=true" \
  --set-secrets="DB_PASSWORD=cloudsql-password-melb:latest" \
  --min-instances=0 \
  --max-instances=5 \
  --memory=512Mi \
  --cpu=1
```

The Cloud Build deployment flow runs `alembic check` before publishing the image.
Pass `_ALEMBIC_DATABASE_URL` for the target staging or production database so the verification step can fail fast on schema drift without applying any migrations.

Deploy the public ingress as a separate Cloud Run service from the same image with the inverse route flags, Firebase env vars, and `--allow-unauthenticated`.
Keep the internal DB/media service IAM-protected and use its canonical service URL for `TAILMATE_DB_GATEWAY_URL`.

Validation notes:

- the Agent Engine runtime service account and the Cloud Run gateway service account are separate concerns; both must be correct
- the public ingress still needs database access because it resolves accounts through `users` plus `user_platform_connections`
- the gateway service account must have storage write access when the internal DB/media route handles uploads
- the gateway `DB_HOST` may point at a different Cloud SQL endpoint than the local proxy path, so the same Alembic head must be applied to that exact endpoint before smoke tests
- use the canonical internal service URL for `TAILMATE_DB_GATEWAY_URL`; keep the Agent Engine ID-token audience aligned with that internal service URL
- Cloud Run IAM is not the only protection boundary anymore; keep the app-layer caller audience aligned with `TAILMATE_DB_GATEWAY_AUTH_AUDIENCE` and keep the write allowlist current

## Deferred Hardening And Troubleshooting

- Cold starts: the current deploy example keeps `--min-instances=0`, so the first request after idle can take a few seconds. This is acceptable for the current smoke-tested path, but if request latency starts approaching the agent timeout budget or gateway startup grows heavier, switch to `--min-instances=1` and account for the steady-state Cloud Run cost.
- Video sanitization: the gateway image now installs `ffmpeg`. If build or deploy changes remove it, video uploads will fail fast with a processing error.
- Secret handling: keep `DB_PASSWORD` wired through Cloud Run Secret Manager integration instead of reverting to plain env vars.
- Runtime identity: if the gateway runs under the default compute service account, uploads can fail even when Agent Engine is configured correctly because the gateway itself still needs bucket write permissions.
- API surface: the gateway intentionally exposes only the public query route and narrow business endpoints. Do not widen it back to raw SQL endpoints such as `/query` or `/execute`; if a future feature needs more access, prefer predefined business endpoints to avoid prompt-injection-driven SQL abuse.
- ID token latency: the current `DbGatewayClient` fetches an ID token per request. This is acceptable unless gateway calls start showing a repeatable per-request auth overhead; if that happens, cache the token until expiry and re-measure before changing anything else.
- Missing-session semantics: `GET /sessions/<session_id>` currently returns `200` with an empty session payload when the record does not exist. Keep that behavior in mind when debugging session-creation flows, because callers cannot distinguish "not found" from "empty new session" without an explicit contract change.
