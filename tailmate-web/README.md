# Tailmate Web

`tailmate-web/` is the owner-facing React SPA for Tailmate.
It consumes the public `/v1/` gateway and implements the Soft Organic design language defined in [`docs/design-spec.md`](docs/design-spec.md).

## Scope

- landing page
- Firebase email-auth login and registration
- protected dashboard
- protected streaming chat
- protected settings and export controls

## Commands

```bash
npm install
npm run dev
npm run typecheck
npm run build
```

## Environment

Create a `.env.local` or equivalent Vite environment file with the Firebase client configuration and service base URLs used by the app:

```bash
VITE_API_BASE_URL=http://localhost:8080
VITE_FIREBASE_API_KEY=...
VITE_FIREBASE_AUTH_DOMAIN=...
VITE_FIREBASE_PROJECT_ID=...
VITE_FIREBASE_APP_ID=...
VITE_FIREBASE_MESSAGING_SENDER_ID=...
```

Self-service registration also requires Firebase Authentication to have the Email/Password
provider enabled for the target project. When Firebase reports that registration is not configured,
the login page now falls back to login-only mode and shows an operator-facing setup hint instead of
repeating the raw SDK error.

## Contract Notes

- use Firebase ID tokens as bearer auth on every `/v1/*` request
- register, then activate, before using protected Tailmate routes
- self-service registration depends on Firebase Authentication Email/Password being enabled for the deployment project
- use `fetch()` streaming for `POST /v1/agent/query`; the public contract is not compatible with native `EventSource`
- media uploads are sent as JSON `strip_metadata_request` payloads, not multipart form data
- the owner-facing public surface is web-only; the retired WhatsApp handoff is no longer supported

## Ownership

- `src/lib/` owns API and Firebase integration
- `src/contexts/` owns auth and local chat state
- `src/hooks/` owns route-facing data flows
- `src/pages/` owns route composition
- `src/components/` owns reusable UI

For the versioned implementation record, see [`docs/tailmate-web-frontend-slice.md`](docs/tailmate-web-frontend-slice.md).
