# Strip Metadata Slice

Version: `v0.14.0`
Status: Sanitized-media slice with owner-scoped upload enforcement and audio transcription

This spec records the `strip_metadata` delivery slice.
It exists to keep the implementation, validation path, and release framing versioned alongside the code.

## Business Goal

Uploaded photos, videos, and voice notes can contain GPS coordinates, device identifiers, timestamps, and other metadata that is irrelevant for Tailmate health analysis but sensitive for user privacy.

The `strip_metadata` slice makes metadata sanitization the first step of media ingestion.
Any media reference returned by Tailmate must point to the sanitized object, not the raw upload.
For supported audio uploads, the same slice attempts a transcription so the normal text routing path can continue without a separate voice-only skill surface, but sanitization success does not depend on transcription availability.

## Slice Mapping

### Contract

- `src/tailmate/contracts/types.py`
  Defines `StripMetadataRequest`, `StripMetadataResult`, and normalization helpers, including the optional `session_id` field plus transcription metadata for downstream tracking.
- `src/tailmate/contracts/errors.py`
  Defines explicit unsupported-media and media-processing error types.
- `src/tailmate/contracts/constants.py`
  Defines the stable skill id, tool id, and metadata keys used across layers.

### Adapter

- `src/tailmate/agent_runtime/ports/sanitized_media_store.py`
  Declares the business-level sanitization port.
- `src/tailmate/adapters/database/media_asset_store.py`
  Persists sanitized upload references to the `media_assets` table for downstream DB readback.
- `src/tailmate/adapters/database/models.py`
  Adds the `media_assets` table metadata.
- `src/tailmate/adapters/database/migrations/versions/46ecbdc4202a_add_media_assets_table_for_strip_metadata.py`
  Creates the checked-in schema revision for `media_assets`.
- `src/tailmate/adapters/media/sanitized_media_store.py`
  Provides local sandbox parity by stripping image/video/audio metadata directly, generating a UUID-backed stored filename, verifying owner access through the dog-profile adapter when available, writing only the clean bytes through the blob-store port, optionally transcribing audio, and persisting the sanitized media reference when the DB adapter is available.
- `src/tailmate/adapters/media/audio_transcriber.py`
  Implements the Gemini-backed audio transcription adapter used after sanitized audio bytes have been produced.
- `src/tailmate/adapters/db_gateway/media_store.py`
  Delegates cloud execution to the Cloud Run gateway.
- `tailmate-db-gateway/main.py`
  Loads the shared Flask gateway app.
- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Implements the cloud upload endpoint that verifies dog ownership, strips EXIF with Pillow, strips video or audio metadata with `ffmpeg -map_metadata -1`, transcribes audio uploads, uploads the clean object to GCS, persists the sanitized reference to `media_assets`, and discards the raw upload.

Schema note:

- This slice changes the database schema and therefore requires the checked-in Alembic migration.

### Skill

- `src/tailmate/skills/strip_metadata_skill.py`
  Exposes the focused `strip_metadata.upload` tool and keeps sanitization logic behind the `SanitizedMediaStore` port.
- `src/tailmate/skills/registry.py`
  Registers the built-in `strip_metadata` capability when the runtime has a supported adapter available.

### Orchestration

- `src/tailmate/agent_runtime/services/graph_orchestrator.py`
  Detects `strip_metadata_request` in the request-scoped metadata bridge, invokes the registered tool, persists the assistant-visible result, stores only the sanitized media reference in session attributes, and for audio uploads either replaces the inbound message with the transcription or degrades gracefully to the normal strip-metadata success turn when no transcription is available.
- `src/tailmate/agents/root/prompts.py`
  Instructs the root agent to route media uploads through `strip_metadata` before any storage or downstream analysis.
- `src/tailmate/agents/root/agent.py`
  Returns the sanitized media result in structured query metadata for both JSON and streaming query flows.

## Validation Path

### Local Sandbox

1. Start the Cloud SQL Auth Proxy with `./scripts/start_cloudsql_proxy.sh`.
2. Apply the schema with `uv run alembic upgrade head`.
3. Run `uv run python src/tailmate/entrypoints/local_dev.py`.
4. Verify the slice with:
   - `uv run python -m compileall src tests tailmate-db-gateway/main.py`
   - `uv run python -m pytest tests/unit`
   - `uv run python -m pytest tests/integration/test_container_modes.py tests/integration/test_strip_metadata_orchestration.py`
   - `uv run python -m pytest tests/contract/test_root_agent_query.py tests/contract/test_skill_registration.py`
5. Run an owner-scoped local upload path such as `uv run tailmate local-demo --file /absolute/path/to/sample.jpg --dog-id demo-dog --user-id <bound-user-id>`.
6. Run the same path with an audio file such as `uv run tailmate local-demo --file /absolute/path/to/sample.m4a --dog-id demo-dog --user-id <bound-user-id>` and confirm the returned strip-metadata payload is successful, with either a non-empty `transcription_text` or `transcription_text=None` when transcription is intentionally unavailable.
7. Optionally inspect a stored sample with `exiftool` and confirm the sanitized asset has no GPS/device/timestamp metadata.

### Cloud Validation

1. Deploy the updated Cloud Run gateway image with `ffmpeg` available.
2. Apply the `media_assets` migration to the target database.
3. Deploy the agent through `deploy-tailmate` with `TAILMATE_DB_GATEWAY_URL` set.
4. Run `deployment/agent_engine/smoke_test.py`.
5. For end-to-end media validation, set both `TAILMATE_SMOKE_MEDIA_PATH` and `TAILMATE_SMOKE_USER_ID=<bound-user-id>` so the smoke test submits a real media file through the owner-scoped `strip_metadata` path.
6. Confirm the returned `media_ref` / `resource_uri` points to the sanitized object in GCS, then inspect that object with `exiftool` or equivalent metadata inspection.
7. For audio rollout, confirm the returned payload includes `transcription_text` when transcription is configured, and confirm that the upload still succeeds with `transcription_text=None` when transcription is intentionally disabled.

## Release Framing

### Cognition

- The root prompt now explicitly treats metadata sanitization as a mandatory prerequisite before media storage or analysis.

### Action

- Tailmate can now strip image EXIF, video metadata, and audio metadata through a registered skill and a cloud-executed upload endpoint.
- Tailmate can now transcribe sanitized audio uploads and feed the resulting text back into the normal runtime route when transcription is available, without making sanitization success depend on that optional step.

### Memory

- Persisted session attributes, caller-visible metadata, and the `media_assets` table now surface only sanitized media references for this flow.
- Audio uploads also persist the sanitized media reference while surfacing transcription metadata, including `transcription_text=None` when no transcription was produced, to the runtime and caller-visible response metadata.
- Sanitized uploads now require a verified owner match before any blob or media row is written.
