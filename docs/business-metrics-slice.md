# Business Metrics Slice

Version: `v0.14.0`
Status: Prometheus-compatible business metrics for the DB gateway and runtime

This spec records the first business-metrics slice for Tailmate.
It exists to keep the metric names, export surface, and validation path versioned alongside the implementation.

## Business Goal

Admins need a small set of durable product metrics to answer basic operational questions without parsing structured logs manually.
The first metrics slice should cover session volume, skill execution outcomes, intent routing, verified knowledge-base usage, and LLM latency by model.

## Slice Mapping

### Contract

- `src/tailmate/metrics.py`
  Owns the in-memory business-metrics registry, Prometheus text exposition, and the counters and histogram used by this slice.
- `src/tailmate/contracts/constants.py`
  Carries the shared route and metadata constants consumed by the gateway and runtime hooks.

### Adapter

- `src/tailmate/adapters/db_gateway/gateway_app.py`
  Exposes the internal `GET /metrics` endpoint and injects channel metadata into public and bridge query requests so the session counter can be labeled correctly.
- `src/tailmate/adapters/conversational_responder.py`
  Records Gemini conversational latency samples by model.
- `src/tailmate/adapters/knowledge_base/retriever.py`
  Records Gemini knowledge-answer latency samples by model.

### Skill

- `src/tailmate/agent_runtime/pipeline/skills/knowledge_base.py`
  Records verified knowledge-base query outcomes by final status.

### Orchestration

- `src/tailmate/agent_runtime/services/graph_orchestrator.py`
  Records new conversation sessions by channel when a session is first created.
- `src/tailmate/agent_runtime/pipeline/steps/intent_classifier_step.py`
  Records resolved intent classifications by classifier and final intent.
- `src/tailmate/agent_runtime/pipeline/steps/skill_execution_step.py`
  Records skill invocation outcomes by skill and status.

## Metric Contract

All metric names use the `tailmate_` prefix.

- `tailmate_sessions_total{channel=...}`
  Counter for new conversation sessions started by channel.
- `tailmate_skill_invocations_total{skill=...,status=...}`
  Counter for skill execution outcomes.
- `tailmate_intent_classifications_total{intent=...,classifier=...}`
  Counter for resolved intent-classification results.
- `tailmate_kb_queries_total{status=...}`
  Counter for verified knowledge-base query outcomes.
- `tailmate_llm_latency_seconds_bucket{model=...,le=...}`
  Histogram for Gemini-backed model latency in seconds, with matching `_sum` and `_count` series.

The internal gateway exports these metrics in standard Prometheus text format at `GET /metrics`.

## Validation Path

### Local Sandbox

1. Run `uv run python -m compileall src tests`.
2. Run `uv run python -m pytest tests/unit/test_metrics.py tests/unit/test_gateway_app.py tests/unit/test_skill_execution_step.py tests/unit/test_llm_intent_classifier.py tests/unit/test_knowledge_retriever.py`.
3. Confirm the gateway `/metrics` response includes the expected `tailmate_` series and Prometheus `# HELP` / `# TYPE` lines.
4. Confirm the runtime hooks increment the expected counters when the orchestrator, skill execution step, and Gemini adapters run.

### Cloud Validation

1. Deploy the internal DB gateway with the metrics endpoint enabled.
2. Scrape `GET /metrics` from an internal IAM-authorized client.
3. Confirm the series are populated after traffic flows through public query, bridge query, and KB-backed turns.

## Release Framing

### Cognition

- Tailmate now treats business metrics as a product contract instead of leaving the counters implicit in logs.

### Action

- The gateway now exposes a Prometheus-compatible metrics endpoint.
- The runtime now records session, skill, intent, KB, and Gemini latency metrics through shared hooks.

### Memory

- Admins can now observe the main product dimensions directly from a stable `/metrics` surface instead of inferring them from request logs.
