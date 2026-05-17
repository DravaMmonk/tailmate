# Tailmate Web Frontend Slice

Version: `v0.16.0`
Status: Implemented

This document records the repository-owned React SPA that serves the owner-facing Tailmate web surface.
The application lives in `tailmate-web/` and is intentionally separate from the Python runtime services so it can evolve as a dedicated frontend delivery unit while consuming the existing public contracts.

## Scope

The web client currently implements:

- a public landing page
- Firebase email-auth login and registration
- a protected dashboard
- a protected streaming chat workspace
- a protected account and export settings surface

The implementation follows the controlled Soft Organic design language in `docs/design-spec.md`.
It does not mix the older dark technical test UI visuals into the production-facing surface.

## Technology Stack

- React `19`
- TypeScript
- Vite
- React Router `v7`
- Tailwind CSS `v4`
- Framer Motion
- Firebase Auth SDK
- `fetch()` + `ReadableStream` SSE parsing for streaming chat
- React Context + `useReducer` for local session state

## Directory Ownership

```text
tailmate-web/
├── public/
├── src/
│   ├── components/
│   ├── contexts/
│   ├── hooks/
│   ├── lib/
│   ├── pages/
│   └── types/
├── index.html
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── vite.config.ts
```

Ownership rules:

- `src/lib/` owns frontend API and Firebase integration.
- `src/contexts/` owns authenticated identity and local chat-session state.
- `src/hooks/` owns composable data flows that bind pages to the public contracts.
- `src/pages/` owns route-level composition only.
- `src/components/` owns reusable UI and route sub-sections.

## Route Map

Public routes:

- `/`
- `/login`

Protected routes:

- `/dashboard`
- `/chat`
- `/chat/:sessionId`
- `/settings`

Protected routes require a valid Firebase identity and are wrapped by `ProtectedRoute` plus `AppLayout`.

## Public Contract Integration

The SPA is intentionally aligned with the currently published gateway and adapter contracts.

### Auth and account lifecycle

- `POST /v1/users/register`
- `POST /v1/users/activate`
- `GET /v1/users/{user_id}/export`
- `DELETE /v1/users/{user_id}`

The frontend treats the Firebase UID as the Tailmate `user_id` for web users.
After Firebase sign-in, the app registers and activates the owner account before exposing the protected workspace.
If Firebase returns `auth/configuration-not-found` or `auth/operation-not-allowed` during a
self-service registration attempt, the login page falls back to login-only mode and surfaces a
deployment setup hint instead of repeating the raw SDK error.

### Streaming chat

- `POST /v1/agent/query`

The chat surface uses `fetch()` streaming instead of native `EventSource`.
That is required because the public query contract is a `POST` request with bearer auth and a JSON body.

The client consumes:

- `query.started`
- `query.delta`
- `query.completed`

Media uploads are tunneled through the same route by populating `strip_metadata_request`.
The frontend does not use multipart upload for the public web flow.

### Channel scope

The owner-facing web client is now the only supported public channel.
The retired WhatsApp handoff route, QR entrypoint fetch, and click-to-chat CTA are no longer part of the supported frontend contract.

## Preview Deployment

Repository preview deployments now use the root `vercel.json` file to override the old Flask preset and build the static SPA from `tailmate-web/`.
The Vercel output directory is `tailmate-web/dist`, and all routes are rewritten to `/index.html` so client-side route refreshes keep working.

## Data Model Boundaries

The current public API does not expose dedicated routes for:

- owner-managed dog-profile CRUD
- session listing outside the privacy export snapshot
- persisted language preference updates

The frontend therefore uses the export snapshot and local session persistence honestly instead of inventing unsupported API surfaces.

## Design System Application

The implementation applies the Soft Organic system through:

- Fraunces headings plus Nunito body text
- parchment backgrounds and forest-green / terracotta accents
- irregular border radii for cards, badges, and navigation
- restrained green-tinted shadows
- glassmorphism on navigation and secondary panels
- grain and blob atmospheric layers
- motion curves based on `cubic-bezier(0.22, 1, 0.36, 1)`

## Validation

Validation executed for this slice:

- `npm run typecheck`
- `npm run build`

Current known caveat:

- the production bundle emits a Vite chunk-size warning because the first SPA cut still ships the full route graph in a single main chunk
- self-service registration still depends on the target Firebase project enabling the Email/Password provider; the frontend only handles the failure path gracefully

## Follow-up Work

- split route bundles to reduce the initial JavaScript payload
- add explicit owner-side dog management routes when the public API exposes them
- add a persisted language-preference path when the backend contract exists
- add end-to-end browser tests for sign-in, export recovery, and streaming chat
