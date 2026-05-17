# Tailmate Vertex Test UI

This Cloud Run service exposes a lightweight browser-based test surface for the deployed Tailmate Vertex AI Agent Engine.
The browser only talks to the Cloud Run service.
The service invokes Agent Engine server-side through ADC, so browser clients never receive Google Cloud credentials.

## Endpoints

- `GET /`
- `GET /statusz`
- `GET /healthz`
- `POST /api/query`

## Required Environment Variables

- `TAILMATE_PROJECT_ID`
- `TAILMATE_LOCATION`
- `TAILMATE_AGENT_ENGINE_RESOURCE_NAME`

## Optional Environment Variables

- `TAILMATE_TEST_UI_TITLE`
- `TAILMATE_TEST_UI_DEFAULT_DOG_ID`
- `TAILMATE_TEST_UI_USER_ID`
- `TAILMATE_TEST_UI_DEFAULT_MESSAGE`
- `TAILMATE_TEST_UI_MAX_UPLOAD_BYTES`

Optional deep-health environment:

- `TAILMATE_DB_GATEWAY_URL`
- `TAILMATE_DB_GATEWAY_TIMEOUT_SECONDS`
- `TAILMATE_MEDIA_BUCKET`

## Behavior

- Text-only requests exercise the standard `query()` path for dog profile creation and enrichment.
- When `TAILMATE_TEST_UI_USER_ID` is set, or when an operator fills the `Trusted User ID` field in the page, the UI injects `metadata["user_id"]` so owner-scoped dog-profile and media flows can be smoke tested without the public Firebase ingress.
- When a file is attached, the service builds `strip_metadata_request` metadata, base64-encodes the uploaded bytes, and forwards the request to the deployed agent.
- The response panel shows the assistant text, structured metadata, and raw JSON for fast smoke testing.
- `GET /healthz` and `GET /statusz` expose deep checks for the configured DB gateway reachability and GCS write/delete access when those environment variables are present, and they return `503` when a configured deep check fails.

## Deploy

```bash
PROJECT_ID=tailmate
REGION=us-central1
SERVICE_NAME=tailmate-vertex-test-ui
SERVICE_ACCOUNT=tailmate-agent-sa@tailmate.iam.gserviceaccount.com
AGENT_RESOURCE_NAME=projects/<project-number>/locations/<region>/reasoningEngines/<engine-id>
IMAGE="us-central1-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/$SERVICE_NAME:$(date +%Y%m%d-%H%M%S)"

gcloud builds submit . \
  --config tailmate-vertex-test-ui/cloudbuild.yaml \
  --substitutions _IMAGE="$IMAGE"

gcloud run deploy $SERVICE_NAME \
  --image="$IMAGE" \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --service-account="$SERVICE_ACCOUNT" \
  --set-env-vars="TAILMATE_PROJECT_ID=$PROJECT_ID,TAILMATE_LOCATION=$REGION,TAILMATE_AGENT_ENGINE_RESOURCE_NAME=$AGENT_RESOURCE_NAME"
```

Operational notes:

- `tailmate-agent-sa@tailmate.iam.gserviceaccount.com` already holds `roles/aiplatform.user` in the current project and is the intended runtime identity for this UI.
- The service is intended as a smoke-test surface, so it should target a specific staged or production Agent Engine resource name instead of discovering the latest deployment implicitly.
- Large uploads inflate after base64 encoding, so raise `TAILMATE_TEST_UI_MAX_UPLOAD_BYTES` only when the Cloud Run request budget and intended test media size justify it.
