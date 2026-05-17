# ADR-0003: Hard Delete Strategy For User Privacy Requests

Status: Accepted

Date: 2026-03-29

## Context

Tailmate now operates in markets that require user-facing privacy workflows such as data export and erasure.
The current persistence model stores user-owned state across PostgreSQL (`users`, `user_platform_connections`, `dog_profiles`, `profile_enrichment_log`, `media_assets`, and `conversation_sessions`), Google Cloud Storage, and Firebase Authentication.

The repository did not yet define whether a user deletion request should:

- soft-delete the relational rows and retain restorable tombstones, or
- hard-delete the owned records and remove external identity plus media objects in the same operational flow.

Because Tailmate is still pre-1.0, it also does not yet have a durable outbox worker, deletion queue, or admin-facing privacy backlog tooling.

## Decision

Tailmate will implement privacy erasure requests as an authenticated hard-delete flow.

The public `/v1/users/<user_id>` delete endpoint must:

1. verify that the Firebase-authenticated caller matches the path `user_id`
2. build a full owner-scoped export snapshot before any destructive action
3. delete owned media objects from the configured blob store with idempotent missing-object handling
4. delete the Firebase Authentication user with idempotent missing-user handling
5. delete the owned PostgreSQL rows in a single database transaction

The public `/v1/users/<user_id>/export` endpoint must return the same owner-scoped snapshot shape without mutating data.

## Rationale

- Privacy law and product expectations favor real erasure over retaining application-visible tombstones.
- The current schema and runtime do not have a safe soft-delete propagation model across dog profiles, conversation sessions, media metadata, and platform bindings.
- Making external cleanup idempotent allows the delete request to be retried safely if a later database operation fails.
- Taking the export snapshot first preserves portability without requiring a separate staging table or asynchronous job runner.

## Consequences

Positive:

- User data export and erasure now share one canonical snapshot format.
- Tailmate removes owner data from PostgreSQL, GCS, and Firebase in one bounded operational path.
- Retry behavior is deterministic because missing blobs or Firebase users are treated as already deleted.

Trade-offs:

- The flow is still synchronous and request-scoped; large accounts may eventually need async orchestration.
- The repository does not yet persist deletion audit tombstones or operator replay jobs.
- If external cleanup succeeds and the later database transaction fails, the request must be retried to complete relational cleanup.

Deferred follow-up:

- add admin-visible deletion telemetry and retry queues when structured logging and distributed tracing land
- evaluate asynchronous deletion jobs once account scale or attachment volume makes the synchronous path too slow
