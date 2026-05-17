from __future__ import annotations

from tailmate.metrics import (
    record_intent_classification,
    record_kb_query,
    record_llm_latency,
    record_session_started,
    record_skill_invocation,
    render_prometheus_metrics,
    reset_metrics_registry,
)


def test_business_metrics_registry_renders_prometheus_text() -> None:
    reset_metrics_registry()

    record_session_started(channel="web")
    record_skill_invocation(skill="dog_profile:create", status="create")
    record_intent_classification(intent="known", classifier="RuleBasedIntentClassifier")
    record_kb_query(status="hit")
    record_llm_latency(model="gemini-2.5-flash", latency_seconds=0.42)

    payload = render_prometheus_metrics()

    assert "# HELP tailmate_sessions_total" in payload
    assert "# TYPE tailmate_sessions_total counter" in payload
    assert 'tailmate_sessions_total{channel="web"} 1' in payload
    assert 'tailmate_skill_invocations_total{skill="dog_profile:create",status="create"} 1' in payload
    assert (
        'tailmate_intent_classifications_total{intent="known",classifier="RuleBasedIntentClassifier"} 1'
        in payload
    )
    assert 'tailmate_kb_queries_total{status="hit"} 1' in payload
    assert 'tailmate_llm_latency_seconds_bucket{model="gemini-2.5-flash",le="0.5"} 1' in payload
    assert 'tailmate_llm_latency_seconds_count{model="gemini-2.5-flash"} 1' in payload
