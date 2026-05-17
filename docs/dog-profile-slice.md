# Dog Profile Slice

Version: `v0.14.0`
Status: Development-stage dog-profile create, active-dog switching, implicit enrichment, and audio-transcribed routing with owner-isolated persistence

This spec records the `dog_profile` delivery slice.
It exists to keep the implementation, validation path, and release framing versioned alongside the code.

## Business Goal

Tailmate should be able to create a dog profile from the minimum possible input and make that profile more complete over time without forcing the user through a form.

The `dog_profile` slice creates a durable dog profile as soon as the user introduces a dog by name.
On later turns in the same session, Tailmate silently extracts new facts from free-form conversation and persists them to the profile record and the enrichment log.
When one owner has multiple dogs, Tailmate now keeps a session-scoped `active_dog_id`, can switch to another known dog by name, and prompts the user to choose when the turn is ambiguous.
When the owner sends an audio note through the sanitized-media path, the resulting transcription now re-enters the same create and enrich route instead of creating a separate dog-profile voice workflow.

## Slice Mapping

### Contract

- `src/tailmate/contracts/dog_profile.py`
  Defines the Pydantic SSOT for `DogProfile`, create and enrich input/output models, extraction results, patch normalization, and summary rendering.
- `src/tailmate/contracts/constants.py`
  Defines the stable skill id, tool ids, and the `dog_profile` response metadata key.

### Adapter

- `src/tailmate/agent_runtime/ports/dog_profile_db_adapter.py`
  Declares the business persistence port used by the skill and gateway, including owner-scoped profile listing for multi-dog switching.
- `src/tailmate/agent_runtime/ports/profile_extractor.py`
  Declares the extraction-strategy port used by the enrichment tool.
- `src/tailmate/adapters/dog_profile/db_adapter.py`
  Persists dog profiles directly through SQLAlchemy, applies merged updates, writes `profile_enrichment_log`, lists owner-scoped profiles for switching, and enforces owner isolation on reads and enrichments.
- `src/tailmate/adapters/dog_profile/extractors.py`
  Implements `RuleBasedExtractor`, `LLMFlashExtractor`, `LLMProExtractor`, and `CompositeExtractor`, plus the implicit create-name detector.
- `src/tailmate/adapters/dog_profile/data/breed_aliases_by_locale.json`
  Stores the multilingual breed alias table used by the deterministic extractor and flattened at runtime by the breed matcher.
- `src/tailmate/adapters/dog_profile/data/extractor_locale_data.json`
  Stores the remaining locale-layered deterministic extractor assets, including keyword families, dog-context hints, numeric-token normalization, and regex patterns that are compiled at runtime instead of being hardcoded inside `extractors.py`.
- `src/tailmate/adapters/db_gateway/dog_profile.py`
  Delegates cloud persistence calls to the Cloud Run gateway.
- `src/tailmate/adapters/db_gateway/client.py`
  Adds typed business endpoints for create, list, load, and enrich profile calls, including the trusted internal owner header.
- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Exposes narrow owner-scoped `dog_profiles` endpoints, including `GET /dog-profiles` for internal active-dog resolution without widening the gateway back into arbitrary SQL.
- `src/tailmate/adapters/database/models.py`
  Adds `dog_profiles` and `profile_enrichment_log` to the canonical runtime metadata.
- `src/tailmate/adapters/database/migrations/versions/9a78bfa8b6e2_add_dog_profile_tables_for_dog_profile_.py`
  Creates the checked-in schema revision for the dog-profile slice.

Schema note:

- This slice changes the database schema and therefore requires the checked-in Alembic migration.

### Skill

- `src/tailmate/skills/dog_profile/manifest.py`
  Registers the `dog_profile` package with the `dog_profile_db_adapter` and `profile_extractor` dependencies.
- `src/tailmate/skills/dog_profile/skill.py`
  Exposes the focused `dog_profile.create` and `dog_profile.enrich` tools and keeps extraction and persistence behind stable ports.
- `src/tailmate/bootstrap/container.py`
  Resolves the configured extraction strategy through `TAILMATE_EXTRACTION_STRATEGY` and builds either the direct or gateway persistence adapter.

### Orchestration

- `src/tailmate/agent_runtime/services/graph_orchestrator.py`
  Detects profile-introduction messages, creates the profile immediately, keeps a session-scoped `active_dog_id`, triggers best-effort enrichment on later turns without blocking the rest of the request path, and routes sanitized audio transcriptions back into the same text-first dog-profile flow.
- `src/tailmate/agent_runtime/pipeline/skills/dog_profile_switch.py`
  Detects explicit and implicit active-dog switching, persists the selected dog across the session, and returns a localized selection prompt when multiple known dogs are available but the user has not specified which one they mean.
- `src/tailmate/agent_runtime/pipeline/skills/_shared.py`
  Centralizes active-dog selection, known-dog name matching, and multi-dog ambiguity handling so recall, enrich, knowledge, and welcome flows all use the same routing decision.
- `src/tailmate/agents/root/prompts.py`
  Documents the implicit create and enrich behavior in operational English.
- `src/tailmate/agents/root/agent.py`
  Returns the created or enriched profile result through structured query metadata, alongside the session-scoped `dog_id`, for both JSON and streaming query flows.

## Validation Path

### Local Sandbox

1. Start the Cloud SQL Auth Proxy with `./scripts/start_cloudsql_proxy.sh`.
2. Apply the schema with `uv run alembic upgrade head`.
3. Run `uv run python -m compileall src tests tailmate-db-gateway/main.py`.
4. Run `uv run python -m pytest tests/unit`.
5. Run `uv run python -m pytest tests/integration tests/contract`.
6. Run a direct local validation path with a bound owner id:
   - create a profile from a minimal name-only input through `uv run tailmate local-demo --message "My dog's name is Bean" --dog-id demo-dog --user-id <bound-user-id>`
   - enrich the same profile from a free-form message such as `Bean is a corgi, 3 years old, 15 kg, and previously had knee surgery`
   - enrich the same profile from mixed deterministic messages such as `Bean is a frenchie boy, desexed, 3 years old and 26 lb`
   - enrich the same profile from Cantonese-style deterministic notes such as `我隻狗係法鬥，好痴身，唔愛郁，而家食狗糧`
   - enrich the same profile from medical and lifestyle messages such as `Bean is allergic to chicken, currently taking Apoquel, and is on a raw diet`
   - create a second profile for the same owner, then confirm `Switch to Bean` or `What breed is Bean?` moves the session `active_dog_id` to the selected known dog without creating a duplicate profile
   - start a fresh session for that same owner and confirm a dog-specific ambiguous turn such as `What is my dog's name?` returns a localized prompt listing the available dog names instead of picking one silently
   - send an audio note such as `Bean is four years old now and weighs fourteen kilograms` through `uv run tailmate local-demo --file /absolute/path/to/sample.m4a --dog-id <bean-dog-id> --user-id <bound-user-id>` and confirm the transcribed text updates the same profile path
   - repeat one read or enrich request with a different trusted user id and confirm the runtime rejects it with `403`
   - read the profile back from Cloud SQL and confirm the structured fields and enrichment log entry were persisted

### Cloud Validation

1. Deploy the updated Cloud Run gateway image so the `dog_profiles` endpoints are available.
2. Apply the `dog_profiles` / `profile_enrichment_log` migration to the database endpoint used by the gateway runtime.
3. Deploy the Agent Engine runtime with the desired `TAILMATE_EXTRACTION_STRATEGY`.
4. Run `deployment/agent_engine/smoke_test.py` against the deployed agent with `TAILMATE_SMOKE_USER_ID=<bound-user-id>` when the turn should create or enrich a profile.
5. Read the created or enriched profile and the associated `profile_enrichment_log` rows back from Cloud SQL.

## Release Framing

### Cognition

- The root runtime now treats dog-profile creation as a minimal-input behavior and profile enrichment as a best-effort background-quality improvement on every later turn.
- The runtime now treats active-dog selection as part of dog-profile cognition, so explicit switch phrases and known-dog name references can redirect later recall and enrich turns onto the correct profile without creating duplicates.
- The runtime now treats sanitized audio transcriptions as first-class dog-profile input, so voice notes can reuse the same create and enrich cognition instead of branching into a separate tool path.
- The deterministic rule layer now uses packaged locale-layered JSON resources for multilingual breed aliases, keyword families, dog-context hints, numeric-token normalization, and regex patterns, including explicit Cantonese (`yue`) coverage alongside Simplified and Traditional Chinese, before escalating harder cases.

### Action

- Tailmate can now create a durable dog profile from a name and progressively enrich it through rule-based or Gemini-backed extraction strategies.
- Tailmate can now list one owner's known dog profiles, switch the session-level `active_dog_id` when the user names a different dog, and ask the user to choose when more than one known dog could fit the turn.
- The rule-based extractor now covers multilingual breed lookup, standardized temperament/activity/diet labels, richer age and weight parsing, and coarse medical extraction that can seed a later Flash escalation.
- The deterministic raw-note path now stores the full dog-context message only when no structured rule matched, so lifestyle facts do not duplicate into both `raw_note` and standardized fields.

### Memory

- Dog profiles now persist in `dog_profiles`, while every enrichment attempt records its extracted field payload, strategy, and confidence in `profile_enrichment_log`.
- The session store now persists `active_dog_id` alongside the legacy `dog_id` field so multi-dog switching stays backward compatible with existing orchestration paths.
- Owner isolation now depends on the canonical `users` binding plus the trusted internal owner header, so dog-profile access no longer trusts caller-supplied body fields alone.
