# ADR-0002: Public API Versioning Strategy

Status: Accepted

## Context

Tailmate now exposes a Firebase-protected public API for account lifecycle and agent-query ingress.
Those routes are consumed by external clients and must support additive iteration without forcing every caller to migrate on every breaking change.

The repository also exposes several IAM-only internal routes for bridge traffic, persistence, and media operations.
Those internal routes are deployed and managed together with Tailmate services, so they do not need the same long-lived compatibility contract as the public ingress.

## Decision

- Public externally consumed routes must be path-versioned under `/vN/`.
- The first stable public contract is `/v1/`.
- The `/v1/` public surface currently includes:
  - `POST /v1/users/register`
  - `POST /v1/users/activate`
  - `POST /v1/users/connections/<platform>`
  - `DELETE /v1/users/connections/<platform>`
  - `POST /v1/agent/query`
- Internal IAM-only routes remain unversioned for now, including `/bridge/*`, `/sessions/*`, `/dog-profiles/*`, `/media/*`, and `/knowledge/*`.
- Breaking public changes must ship on a new path version such as `/v2/` instead of mutating `/v1/` in place.
- Additive non-breaking changes may remain within the active public version as long as the documented request and response contracts stay backward compatible.

## Migration Policy

- Before a new public major path version is published, keep the previous public version available during the migration window unless there is a security or legal reason to remove it immediately.
- New public clients must target the latest documented `/vN/` path family directly.
- Internal adapters such as the WhatsApp bridge do not consume the public ingress and therefore are not required to move with public path-version upgrades.
- Documentation for any new public version must explicitly describe the boundary between public path-versioned routes and private unversioned IAM routes.

## Consequences

- Future work such as rate limiting and streaming can now target `/v1/` without ambiguity.
- External clients gain a durable compatibility boundary.
- Internal service-to-service APIs remain free to evolve quickly while we are still converging on the private operational contract.
