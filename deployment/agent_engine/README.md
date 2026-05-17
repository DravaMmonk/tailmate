# Agent Engine Deployment

This directory owns deployment-specific assets for Vertex AI Agent Engine.
This file is a controlled deployment document and must be updated in the same Pull Request as any deployment contract change.

Rules:

- deploy the root agent only through the custom agent application boundary
- preserve the `set_up()` initialization model required by Agent Engine
- keep runtime packaging separate from feature modules
- deploy new product versions to a non-production target first
- validate regression prompts and tool execution before moving the production alias
- force `TAILMATE_ENV=CLOUD` in the deployment entrypoint before building the deployable app
- reject deployment configuration that is missing either direct database settings or `TAILMATE_DB_GATEWAY_URL`, plus the cloud media bucket
- require `TAILMATE_DB_IP` to be a private IP address in `CLOUD` mode when direct database access is used; this must be a Cloud SQL private IP reachable from the configured network attachment
- standardize `TAILMATE_NETWORK_ATTACHMENT` on the full `projects/{project}/regions/{region}/networkAttachments/{name}` resource path for direct private-IP deployments
- disable `pscInterfaceConfig` automatically when `TAILMATE_DB_GATEWAY_URL` is set
- do not require DNS peering for the regional baseline when the runtime connects directly to a private endpoint IP
- require `TAILMATE_DNS_PEERING_DOMAIN`, `TAILMATE_DNS_PEERING_TARGET_PROJECT`, and `TAILMATE_DNS_PEERING_TARGET_NETWORK` to be set together when private Cloud DNS peering is needed for direct PSC deployments
- use a PSC network attachment subnet on routable RFC 1918 space; Google recommends a `/28` subnet for Vertex AI PSC interfaces
- ensure the Vertex AI service agent has `roles/compute.networkAdmin` in the network attachment project and `roles/dns.peer` when DNS peering is configured
- in Shared VPC topologies, ensure the Vertex AI service agent also has `roles/compute.networkUser` in the host project
- prefer `TAILMATE_DB_PASSWORD=projects/.../secrets/.../versions/...` so the runtime resolves the secret from Secret Manager
- when gateway mode is enabled, point `TAILMATE_DB_GATEWAY_URL` at the Cloud Run service URL and grant the Agent Engine runtime service account `roles/run.invoker`
- deploy with a dedicated service account declared through `TAILMATE_SERVICE_ACCOUNT` or `SERVICE_ACCOUNT`
- for gateway mode, do not rely on the default Reasoning Engine identity if the gateway IAM policy expects a dedicated runtime service account such as `tailmate-agent-sa@tailmate.iam.gserviceaccount.com`
- pass `TAILMATE_ENABLED_SKILLS` and `TAILMATE_DISABLED_SKILLS` through deployment `envVars` whenever rollout state differs from defaults, so cloud behavior matches the reviewed release intent
- pass `TAILMATE_EXTRACTION_STRATEGY`, `TAILMATE_GEMINI_FLASH_MODEL`, `TAILMATE_GEMINI_PRO_MODEL`, and `TAILMATE_GEMINI_TIMEOUT_SECONDS` through deployment `envVars` so dog-profile extraction behavior does not drift between local validation and cloud runtime
- pass `TAILMATE_KB_ENABLED`, `TAILMATE_EMBEDDING_MODEL`, and `TAILMATE_KB_THRESHOLD` through deployment `envVars` when the verified knowledge base should be active, so the orchestrator port, embedding model, and similarity cutoff match the reviewed release intent
- prefer Vertex AI native authentication through ADC and the deployed runtime service account for Gemini extraction; Agent Engine deployments should not pass `TAILMATE_GEMINI_API_KEY` through `envVars`
- when `TAILMATE_KB_ENABLED=true`, make sure the runtime can reach Vertex AI for embeddings and answer synthesis through ADC or `TAILMATE_GEMINI_API_KEY`, just like the other Gemini-backed paths
- pass `TAILMATE_DB_CONNECT_TIMEOUT_SECONDS` and `TAILMATE_DB_SSLMODE` through deployment `envVars` when direct Cloud SQL connectivity uses non-default tuning
- keep `deployment/agent_engine/requirements.txt` synchronized from `uv.lock` through `python scripts/sync_agent_engine_requirements.py`
- pin the deployment interpreter to Python `3.11`
- rebuild the local deployment environment with `uv sync --python /path/to/python3.11` before publishing
- invoke deployment commands through `uv run --python /path/to/python3.11` so local `cloudpickle`, `pydantic`, and `tailmate-app` match the locked runtime
- keep source-based deployment pointed at `tailmate.entrypoints.root_app:app` so the packaged module tree remains explicit and reviewable
- keep the default Agent Engine display name and description version-aligned with `pyproject.toml`; override them only for staged rollout targets such as `staging` or pre-release builds like `v0.6.0-rc.1`
- use `deployment/agent_engine/smoke_test.py` to verify the deployed agent through `vertexai.Client(...).agent_engines.get(...).query(...)`
- `deployment/agent_engine/smoke_test.py` loads `.env` before evaluating its required variables, but CI or production validation should still pass explicit environment variables for reproducibility
- when validating `strip_metadata`, provide `TAILMATE_SMOKE_MEDIA_PATH` and optionally `TAILMATE_SMOKE_MEDIA_CONTENT_TYPE` / `TAILMATE_SMOKE_RESOURCE_KIND` so the smoke test sends a real media payload through the registered skill
- when validating `dog_profile`, set `TAILMATE_SMOKE_MESSAGE` to a create-or-enrich utterance such as `My dog's name is Bean` or `Bean is a corgi, 3 years old, 15 kg`, and set `TAILMATE_SMOKE_USER_ID` to a bound owner when the flow depends on dog-profile or media ownership
- when validating the verified knowledge base, enable `TAILMATE_KB_ENABLED=true`, seed reviewed JSONL chunks into `knowledge_chunks`, and check both direct and gateway routes by confirming hit, out-of-scope, and deterministic fallback behavior
- confirm the response metadata includes `dog_id` plus `dog_profile_result`, and keep `TAILMATE_SMOKE_USER_ID` empty only for turns that do not require owner-scoped tools
- keep reserved Google-managed env vars such as `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `CLOUD_ML_REGION`, and `GOOGLE_APPLICATION_CREDENTIALS` out of Agent Engine `envVars`
