# ADR-0001: Reject Direct-to-GCS Signed Uploads and Firestore Migration

Status: Accepted
Date: 2026-03-27
Deciders: Engineering
Related Issue: `#17`

## Context

Two shortcuts were proposed for the current Tailmate baseline:

1. let clients upload media directly to Google Cloud Storage through signed URLs
2. replace Cloud SQL PostgreSQL with Firestore to reduce operational overhead

Both proposals conflict with the repository's current privacy and persistence contracts.
This ADR records the accepted decision so future feature work does not reopen the same debate without a new architecture review.

## Decision 1: Reject direct-to-GCS signed URL upload

### Decision

Rejected.

### Rationale

The cloud upload path is intentionally:

`Client -> POST /media/upload -> sanitize on the server -> store only sanitized bytes in GCS`

The current implementation enforces that boundary in:

- `src/tailmate/adapters/db_gateway/gateway_app.py`, where `POST /media/upload` and `POST /media/strip-metadata` route uploads through the sanitization flow before persistence
- `src/tailmate/adapters/media/sanitized_media_store.py`, where images are rewritten through Pillow and videos are rewritten through `ffmpeg -map_metadata -1` before storage

Direct signed uploads would allow unsanitized bytes to land in durable object storage before Tailmate removes EXIF or container metadata.
That is incompatible with the current privacy contract because image metadata can contain GPS coordinates, device identifiers, and timestamps.

No throughput or cost optimization justifies storing user media in an unsanitized form.

### Approved Alternative

If upload volume outgrows the current `db-gateway` deployment, split media ingestion into a dedicated Cloud Run service that keeps the same receive -> sanitize -> store contract.
Any future scaling work must preserve the sanitize-before-store invariant.

## Decision 2: Reject Firestore migration from Cloud SQL PostgreSQL

### Decision

Rejected.

### Rationale

The current persistence layer is tightly coupled to PostgreSQL and its surrounding tooling:

- `src/tailmate/adapters/db_gateway/gateway_app.py` uses PostgreSQL `ON CONFLICT ... DO UPDATE` upsert syntax for session persistence
- `src/tailmate/adapters/database/models.py` uses PostgreSQL `JSONB` variants for profile and enrichment payloads
- `alembic.ini` and `src/tailmate/adapters/database/migrations/` define an Alembic-managed relational schema history
- `pyproject.toml`, `src/tailmate/bootstrap/container.py`, and `src/tailmate/adapters/db_gateway/gateway_app.py` wire PostgreSQL drivers and SQLAlchemy database URLs

Moving to Firestore would require a full rewrite of the data model, query layer, migration flow, and operational tooling without adding a functional advantage for the current product scope.

### Approved Path

Continue using Cloud SQL PostgreSQL as the durable store.
If operational pressure grows, address it with PostgreSQL-native measures such as connection pooling, instance tuning, read replicas, or service decomposition instead of replacing the database engine.

## Consequences

- `POST /media/upload` remains the mandatory cloud ingress path for media files.
- Future media-ingestion work must preserve server-side sanitization before any durable storage write.
- The approved persistence baseline remains Cloud SQL PostgreSQL with SQLAlchemy and Alembic.
