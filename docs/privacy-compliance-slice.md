# Privacy Compliance Slice

Version: `v0.11.0`
Status: Public `/v1/` data export and hard-delete privacy workflows for Firebase-authenticated users

This spec records the first privacy-compliance slice for Tailmate.
It exists to keep the user-export contract, hard-delete sequencing, external cleanup behavior, and validation path versioned alongside the implementation.

## Business Goal

Tailmate must support owner-initiated privacy requests for data portability and erasure.
Those requests must cover the persisted master account, platform connections, dog profiles, enrichment history, media metadata, stored media objects, and conversation sessions without exposing internal-only routes to arbitrary callers.

## Slice Mapping

### Contract

- `src/tailmate/contracts/constants.py`
  Defines the versioned public privacy paths `GET /v1/users/<user_id>/export` and `DELETE /v1/users/<user_id>`.
- `docs/adr-0003-hard-delete-user-privacy-requests.md`
  Records the accepted hard-delete strategy, sequencing, and idempotency rules for privacy requests.

### Adapter

- `src/tailmate/adapters/db_gateway/privacy.py`
  Owns the canonical privacy snapshot format, owner-scoped SQL export queries, blob cleanup, Firebase deletion, and transactional relational hard-delete.
- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Exposes the public export and delete routes, verifies that the Firebase-authenticated caller matches the requested `user_id`, and wires the privacy service lazily so the existing public query tests do not need database or blob-store setup.
- `src/tailmate/adapters/gcs/gcs_adapter.py`
  Treats missing objects as already deleted so privacy retries remain safe after partial external cleanup.
- `pyproject.toml`
  Adds the `firebase-admin` dependency required for server-side Firebase account deletion.

### Skill

- No new runtime skill is introduced in this slice.
- Privacy requests terminate at the public gateway boundary rather than through agent orchestration.

### Orchestration

- No graph-level routing changes are required for this slice.
- The public gateway now owns user-account export and erasure as first-class lifecycle operations beside registration, activation, and agent query ingress.

## Public Export Contract

`GET /v1/users/<user_id>/export`

- requires `Authorization: Bearer <Firebase ID token>`
- requires the authenticated Firebase `uid` to match the route `user_id`
- returns:
  - `user`
  - `platform_connections`
  - `dog_profiles`
  - `profile_enrichment_log`
  - `media_assets`
  - `conversation_sessions`
  - `format_version`
  - `exported_at`

The response is owner-scoped.
No other user's rows, sessions, or media metadata may appear in the export.

## Public Delete Contract

`DELETE /v1/users/<user_id>`

- requires `Authorization: Bearer <Firebase ID token>`
- requires the authenticated Firebase `uid` to match the route `user_id`
- executes the accepted hard-delete sequence from ADR-0003
- returns a deletion summary with:
  - `deleted`
  - `user_id`
  - `deleted_at`
  - `counts`
  - `blob_objects_deleted`
  - `firebase_user_deleted`

Deletion scope:

- `users`
- `user_platform_connections`
- `dog_profiles`
- `profile_enrichment_log`
- `media_assets`
- `conversation_sessions`
- owned media objects in blob storage
- the Firebase Authentication user

## Validation Path

### Local Sandbox

1. Install dependencies so `firebase-admin` is available to the gateway environment.
2. Start the Cloud SQL Auth Proxy with `./scripts/start_cloudsql_proxy.sh`.
3. Run `uv run python -m compileall src tests tailmate-db-gateway/main.py`.
4. Run `uv run python -m pytest tests/unit/test_gateway_app.py tests/unit/test_gcs_adapter.py tests/integration/test_user_privacy_gateway.py`.
5. Validate the export route with a Firebase-authenticated user whose `uid` matches the requested path user id.
6. Validate the delete route against a seeded test user and confirm:
   - the returned counts match the seeded account footprint
   - the related blobs are deleted
   - a second delete retry is safe when the external resources are already absent

### Cloud Validation

1. Deploy the public gateway with Firebase ingress enabled and the media bucket configured in the environment.
2. Verify `GET /v1/users/<user_id>/export` returns only the authenticated caller's data.
3. Verify `DELETE /v1/users/<user_id>` removes the caller's GCS media objects, Firebase identity, and relational data.
4. Confirm unrelated users, dogs, media rows, and sessions remain intact after the delete request.

## Release Framing

### Cognition

- Tailmate now treats privacy export and erasure as explicit account lifecycle capabilities instead of an undefined operator-only cleanup task.

### Action

- The public gateway can now export owner data and execute authenticated hard deletes across PostgreSQL, GCS, and Firebase.
- Missing external resources are treated as already deleted so the workflow can be retried safely.

### Memory

- The privacy export response now defines the portable account snapshot for users and operators.
- Conversation sessions, dog profiles, enrichment history, and media metadata now share one deletion boundary tied to the master user account.
