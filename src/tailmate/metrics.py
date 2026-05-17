"""Business metrics registry and Prometheus text export helpers."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import isfinite
from threading import RLock
from typing import Any


DEFAULT_LLM_LATENCY_BUCKETS: tuple[float, ...] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)


def _normalize_label_value(value: Any) -> str:
    normalized = str(value).strip()
    return normalized or "unknown"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".12g")


@dataclass
class CounterMetric:
    """In-memory counter series keyed by a fixed label set."""

    name: str
    help_text: str
    label_names: tuple[str, ...]

    def __post_init__(self) -> None:
        self._values: dict[tuple[str, ...], float] = defaultdict(float)
        self._lock = RLock()

    def inc(self, *, labels: tuple[Any, ...], amount: float = 1.0) -> None:
        if len(labels) != len(self.label_names):
            raise ValueError(f"{self.name} expects {len(self.label_names)} labels.")
        if amount <= 0:
            return
        normalized_labels = tuple(_normalize_label_value(label) for label in labels)
        with self._lock:
            self._values[normalized_labels] += amount

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        for labels, value in sorted(self._values.items()):
            lines.append(f"{self.name}{self._format_labels(labels)} {_format_number(value)}")
        return lines

    def _format_labels(self, labels: tuple[str, ...]) -> str:
        if not labels:
            return ""
        parts = [
            f'{name}="{_escape_label_value(value)}"'
            for name, value in zip(self.label_names, labels, strict=True)
        ]
        return "{" + ",".join(parts) + "}"


@dataclass
class HistogramSample:
    """Bucketed histogram series for one label combination."""

    buckets: list[int]
    count: int = 0
    sum: float = 0.0


class HistogramMetric:
    """In-memory histogram series keyed by a fixed label set."""

    def __init__(self, name: str, help_text: str, label_names: tuple[str, ...], buckets: tuple[float, ...]):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self.buckets = buckets
        self._values: dict[tuple[str, ...], HistogramSample] = {}
        self._lock = RLock()

    def observe(self, *, labels: tuple[Any, ...], value: float) -> None:
        if len(labels) != len(self.label_names):
            raise ValueError(f"{self.name} expects {len(self.label_names)} labels.")
        if not isfinite(value):
            return
        normalized_labels = tuple(_normalize_label_value(label) for label in labels)
        with self._lock:
            sample = self._values.get(normalized_labels)
            if sample is None:
                sample = HistogramSample(buckets=[0] * (len(self.buckets) + 1))
                self._values[normalized_labels] = sample
            sample.count += 1
            sample.sum += max(value, 0.0)
            observed = max(value, 0.0)
            for index, bucket in enumerate(self.buckets):
                if observed <= bucket:
                    sample.buckets[index] += 1
                    break
            else:
                sample.buckets[-1] += 1

    def render(self) -> list[str]:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        for labels, sample in sorted(self._values.items()):
            cumulative = 0
            base_labels = self._format_label_pairs(labels)
            for bucket, bucket_count in zip(self.buckets, sample.buckets[:-1], strict=True):
                cumulative += bucket_count
                lines.append(
                    f"{self.name}_bucket{self._format_labels(base_labels, extra=(('le', _format_bucket_limit(bucket)),))} {_format_number(float(cumulative))}"
                )
            cumulative += sample.buckets[-1]
            lines.append(
                f"{self.name}_bucket{self._format_labels(base_labels, extra=(('le', '+Inf'),))} {_format_number(float(cumulative))}"
            )
            lines.append(f"{self.name}_sum{self._format_labels(base_labels)} {_format_number(sample.sum)}")
            lines.append(
                f"{self.name}_count{self._format_labels(base_labels)} {_format_number(float(sample.count))}"
            )
        return lines

    def _format_label_pairs(self, labels: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(
            (name, _escape_label_value(value))
            for name, value in zip(self.label_names, labels, strict=True)
        )

    @staticmethod
    def _format_labels(
        labels: tuple[tuple[str, str], ...],
        *,
        extra: tuple[tuple[str, str], ...] = (),
    ) -> str:
        combined = labels + extra
        if not combined:
            return ""
        parts = [f'{name}="{value}"' for name, value in combined]
        return "{" + ",".join(parts) + "}"


def _format_bucket_limit(bucket: float) -> str:
    if bucket.is_integer():
        return str(int(bucket))
    return format(bucket, ".12g")


class MetricsRegistry:
    """Business metrics registry with Prometheus exposition formatting."""

    def __init__(self) -> None:
        self.sessions_total = CounterMetric(
            name="tailmate_sessions_total",
            help_text="Total number of new conversation sessions started by channel.",
            label_names=("channel",),
        )
        self.skill_invocations_total = CounterMetric(
            name="tailmate_skill_invocations_total",
            help_text="Total number of skill executions by skill and final status.",
            label_names=("skill", "status"),
        )
        self.intent_classifications_total = CounterMetric(
            name="tailmate_intent_classifications_total",
            help_text="Total number of intent classifications by resolved intent and classifier.",
            label_names=("intent", "classifier"),
        )
        self.kb_queries_total = CounterMetric(
            name="tailmate_kb_queries_total",
            help_text="Total number of verified knowledge-base queries by final status.",
            label_names=("status",),
        )
        self.llm_latency_seconds = HistogramMetric(
            name="tailmate_llm_latency_seconds",
            help_text="Latency in seconds for LLM-backed model calls, bucketed by model.",
            label_names=("model",),
            buckets=DEFAULT_LLM_LATENCY_BUCKETS,
        )

    def render(self) -> str:
        lines: list[str] = []
        lines.extend(self.sessions_total.render())
        lines.extend(self.skill_invocations_total.render())
        lines.extend(self.intent_classifications_total.render())
        lines.extend(self.kb_queries_total.render())
        lines.extend(self.llm_latency_seconds.render())
        return "\n".join(lines) + "\n"


_registry = MetricsRegistry()
_registry_lock = RLock()


def get_metrics_registry() -> MetricsRegistry:
    """Return the active business metrics registry."""

    return _registry


def set_metrics_registry(registry: MetricsRegistry) -> None:
    """Install a custom registry, primarily for tests."""

    global _registry
    with _registry_lock:
        _registry = registry


def reset_metrics_registry() -> MetricsRegistry:
    """Replace the active registry with a fresh, empty instance."""

    registry = MetricsRegistry()
    set_metrics_registry(registry)
    return registry


def record_session_started(*, channel: str) -> None:
    """Increment the session-start counter for one channel."""

    get_metrics_registry().sessions_total.inc(labels=(channel,))


def record_skill_invocation(*, skill: str, status: str) -> None:
    """Increment the skill execution counter for one skill outcome."""

    get_metrics_registry().skill_invocations_total.inc(labels=(skill, status))


def record_intent_classification(*, intent: str, classifier: str) -> None:
    """Increment the intent-classification counter for one classifier result."""

    get_metrics_registry().intent_classifications_total.inc(labels=(intent, classifier))


def record_kb_query(*, status: str) -> None:
    """Increment the verified knowledge-base query counter."""

    get_metrics_registry().kb_queries_total.inc(labels=(status,))


def record_llm_latency(*, model: str, latency_seconds: float) -> None:
    """Record one Gemini or LLM call latency sample."""

    get_metrics_registry().llm_latency_seconds.observe(labels=(model,), value=latency_seconds)


def render_prometheus_metrics() -> str:
    """Render the active registry in Prometheus text exposition format."""

    return get_metrics_registry().render()


def resolve_classifier_metric_name(classifier: Any) -> str:
    """Return a stable classifier label for business metrics."""

    metric_name = getattr(classifier, "metric_name", None)
    if isinstance(metric_name, str) and metric_name.strip():
        return metric_name.strip()
    return type(classifier).__name__
