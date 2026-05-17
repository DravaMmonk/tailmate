"""OpenTelemetry tracing helpers shared across Tailmate services."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping
from contextlib import contextmanager
import os
from threading import RLock
from typing import Any

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.context import Context, Token
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.resources import DEPLOYMENT_ENVIRONMENT, Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.trace import Span, SpanKind, format_span_id, format_trace_id
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from tailmate.bootstrap.config import AppEnvironment


_tracing_lock = RLock()
_tracer_provider: TracerProvider | None = None
_trace_propagator = TraceContextTextMapPropagator()


def _resolve_environment(environment: AppEnvironment | None = None) -> AppEnvironment:
    if environment is not None:
        return environment
    raw_environment = os.getenv("TAILMATE_ENV", AppEnvironment.CLOUD.value).strip().upper()
    try:
        return AppEnvironment(raw_environment)
    except Exception:
        return AppEnvironment.CLOUD


def _build_span_exporter(environment: AppEnvironment) -> Any:
    if environment is AppEnvironment.LOCAL or os.getenv("PYTEST_CURRENT_TEST"):
        return ConsoleSpanExporter()
    return CloudTraceSpanExporter()


def configure_tracing(
    *,
    environment: AppEnvironment | None = None,
    service_name: str = "tailmate",
    service_version: str | None = None,
    force: bool = False,
) -> TracerProvider:
    """Configure the shared tracer provider once per process."""

    global _tracer_provider
    resolved_environment = _resolve_environment(environment)

    with _tracing_lock:
        if _tracer_provider is not None and not force:
            return _tracer_provider

        resource_attributes: dict[str, str] = {SERVICE_NAME: service_name}
        if service_version:
            resource_attributes[SERVICE_VERSION] = service_version
        resource_attributes[DEPLOYMENT_ENVIRONMENT] = resolved_environment.value.lower()

        provider = TracerProvider(resource=Resource.create(resource_attributes))
        span_exporter = _build_span_exporter(resolved_environment)
        if resolved_environment is AppEnvironment.LOCAL or os.getenv("PYTEST_CURRENT_TEST"):
            provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        else:
            provider.add_span_processor(BatchSpanProcessor(span_exporter))

        _tracer_provider = provider
        set_global_textmap(_trace_propagator)
        return provider


def get_tracer(name: str, version: str | None = None):
    """Return a tracer from the configured provider or the process default."""

    provider = _tracer_provider
    if provider is None:
        return trace.get_tracer(name, version)
    return provider.get_tracer(name, version)


def extract_trace_context(carrier: Mapping[str, Any]) -> Context:
    """Extract an OpenTelemetry context from a mapping carrier."""

    return _trace_propagator.extract(carrier=carrier)


def attach_trace_context(carrier: Mapping[str, Any]) -> Token[Context]:
    """Attach an extracted context as the active parent span context."""

    return otel_context.attach(extract_trace_context(carrier))


def detach_trace_context(token: Token[Context]) -> None:
    """Detach a context token previously returned by attach_trace_context."""

    otel_context.detach(token)


def inject_trace_context(carrier: MutableMapping[str, Any]) -> None:
    """Inject the current trace context into a mutable carrier."""

    _trace_propagator.inject(carrier)


def current_trace_fields() -> dict[str, str]:
    """Return the active trace identifiers for structured logs."""

    span = trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context.is_valid:
        return {}
    return {
        "trace_id": format_trace_id(span_context.trace_id),
        "span_id": format_span_id(span_context.span_id),
    }


@contextmanager
def start_span(
    name: str,
    *,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Mapping[str, Any] | None = None,
    context: Context | None = None,
) -> Iterator[Span]:
    """Start a child span and expose it as the active span within the block."""

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span(
        name,
        kind=kind,
        context=context,
        attributes=dict(attributes or {}),
    ) as span:
        yield span
