# Observability Slice

Version: `v0.15.0`
Status: Structured JSON logs, request and trace correlation, and distributed tracing across gateway, runtime, and adapters

This spec records the first structured-observability slice for Tailmate.
It exists to keep the shared log shape, request-correlation contract, and validation path versioned alongside the implementation.

## Business Goal

Admins need to trace one request across the public gateway, the agent runtime, and the WhatsApp adapter without relying on free-form text logs.
Tailmate therefore needs a single structured logging baseline with request correlation, a consistent minimum field set, and trace spans that let operators follow one request across service and adapter boundaries.

## Slice Mapping

### Contract

- `src/tailmate/contracts/constants.py`
  Defines the shared `X-Tailmate-Request-Id` and `X-Trace-Id` headers plus the propagated `traceparent` and `tracestate` metadata keys used for service-to-service correlation.
- `src/tailmate/agent_runtime/current_context.py`
  Extends the runtime request context with `request_id` and `trace_id` so the agent execution path can keep correlation ids bound to one turn.
- `src/tailmate/tracing.py`
  Defines the shared OpenTelemetry tracer provider, W3C trace-context propagation helpers, span helpers, and process-wide tracing configuration.

### Adapter

- `src/tailmate/observability.py`
  Owns the shared JSON log formatter, request-scoped log context, request and trace id generation, root logger configuration, and log-level trace id / span id enrichment.
- `src/tailmate/adapters/vertex_agent_engine/observability.py`
  Replaces the no-op cloud observability shim with structured `record_event()` and `record_error()` emission while configuring tracing for the Agent Engine runtime.
- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Generates or accepts both request and trace ids, extracts incoming W3C trace context, binds all correlation fields to Flask request scope, injects the active trace context into downstream agent metadata, wraps key request paths in spans, logs request completion with latency, and returns the correlation headers to callers.
- `src/tailmate/adapters/db_gateway/client.py`
  Propagates the current request id, current trace id, and active trace context to internal gateway calls and wraps HTTP calls in a child span.
- `src/tailmate/adapters/database/conversation_store.py`
  Wraps session load and save paths in database spans so conversation-state latency is visible in traces.
- `src/tailmate/adapters/database/media_asset_store.py`
  Wraps media persistence writes in spans so sanitized upload persistence can be correlated with the request trace.
- `src/tailmate/adapters/gcs/gcs_adapter.py`
  Wraps upload and delete operations in spans so blob-storage latency is visible alongside request logs.
- `src/tailmate/adapters/whatsapp/app.py`
  Binds structured request and trace context for webhook and health requests, claims duplicate webhook message ids before processing, logs request completion with latency, and returns the correlation headers to callers.

### Skill

- No new business skill is introduced in this slice.
- Existing runtime-skill events now inherit request, user, session, skill, and intent context from the shared logger.

### Orchestration

- `src/tailmate/agents/root/agent.py`
  Generates request and trace ids when they are not already present, preserves incoming trace metadata, and binds the context into both runtime execution and the shared log context.
- `src/tailmate/agent_runtime/services/graph_orchestrator.py`
  Adds `intent`, `skill`, and `latency_ms` fields to the top-level orchestrator run and fallback events while preserving trace-aware request metadata through both JSON and SSE query flows.

## Structured Log Baseline

Every structured log line now uses JSON and may include:

- `timestamp`
- `level`
- `logger`
- `event`
- `message`
- `request_id`
- `trace_id`
- `span_id`
- `user_id`
- `session_id`
- `skill`
- `intent`
- `latency_ms`

Additional event-specific fields are allowed so long as the baseline correlation fields remain stable.

## Request Correlation Rules

- Public and internal HTTP services accept `X-Tailmate-Request-Id` when supplied.
- Public and internal HTTP services accept `X-Trace-Id` when supplied.
- Public and internal HTTP services accept `traceparent` and optional `tracestate` when supplied.
- Services generate a new request id when the header is absent.
- Services generate a new trace id when the header is absent.
- The DB gateway injects the request id into agent-query metadata so the remote agent execution path keeps the same correlation id.
- The DB gateway injects the trace id into agent-query metadata so the remote agent execution path keeps the same trace-level correlation id.
- The DB gateway injects the active W3C trace context into downstream agent metadata so the remote agent execution path can attach to the same trace tree.
- Internal gateway clients forward the current request id, current trace id, and the active W3C trace context when one is bound to the current request.
- HTTP responses from the gateway and WhatsApp adapter return the effective `X-Tailmate-Request-Id` and `X-Trace-Id` headers.

## Validation Path

### Local Sandbox

1. Run `uv run python -m compileall src`.
2. Run `uv run python -m pytest tests/unit/test_observability.py tests/unit/test_db_gateway_client.py tests/unit/test_gateway_app.py tests/unit/test_whatsapp_adapter.py`.
3. Confirm the gateway public query and bridge query tests preserve the same request id and trace id in both the response headers and the agent payload metadata.
4. Confirm the gateway request metadata also carries a `traceparent` value into the downstream agent payload.
5. Confirm the WhatsApp webhook duplicate test returns `200` without a second bridge call and that the structured warning log keeps the active `trace_id`.
6. Confirm the WhatsApp webhook test returns `X-Tailmate-Request-Id` and `X-Trace-Id` while preserving the existing bridge behavior.

### Cloud Validation

1. Deploy the updated public gateway, internal gateway, and WhatsApp adapter services.
2. Send a request with a known `X-Tailmate-Request-Id`, `X-Trace-Id`, and `traceparent` and confirm the same ids and trace appear in:
   - gateway request-completion logs
   - downstream agent runtime logs
   - any internal gateway calls made by the WhatsApp adapter
   - Cloud Trace spans emitted by the gateway, database, and blob-storage paths
3. Confirm Cloud Logging filters can target:
   - one `request_id`
   - one `session_id`
   - one `intent`
   - one `skill`

## Release Framing

### Cognition

- Tailmate now treats observability as a shared product contract instead of leaving correlation and log shape to per-module ad hoc logging.

### Action

- The gateway and WhatsApp adapter now emit structured request lifecycle logs with `request_id`, `trace_id`, and `latency_ms`.
- The agent runtime now carries the same request and trace ids into orchestrator logs and downstream gateway calls.
- The gateway, database, and storage adapters now emit OpenTelemetry spans under the same propagated trace context.

### Memory

- Admins can now reconstruct one request's path across multiple services using a stable correlation id instead of only raw timestamps and free-form messages.
