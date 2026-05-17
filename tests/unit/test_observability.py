from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import json
import logging

from tailmate.adapters.vertex_agent_engine import observability as runtime_observability
from tailmate.observability import (
    JsonLogFormatter,
    LogContext,
    generate_request_id,
    generate_trace_id,
    reset_log_context,
    set_log_context,
)


def test_json_log_formatter_includes_bound_request_context_and_aliases() -> None:
    token = set_log_context(
        LogContext(
            request_id="req-1",
            trace_id="trace-1",
            user_id="user-1",
            session_id="session-1",
        )
    )
    try:
        record = logging.makeLogRecord(
            {
                "name": "tailmate.runtime",
                "levelno": logging.INFO,
                "levelname": "INFO",
                "msg": "orchestrator_skill_executed",
                "skill_id": "dog_profile",
                "duration_ms": 42,
            }
        )
        payload = json.loads(JsonLogFormatter().format(record))
    finally:
        reset_log_context(token)

    assert payload["event"] == "orchestrator_skill_executed"
    assert payload["message"] == "orchestrator_skill_executed"
    assert payload["request_id"] == "req-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["user_id"] == "user-1"
    assert payload["session_id"] == "session-1"
    assert payload["skill"] == "dog_profile"
    assert payload["latency_ms"] == 42


def test_json_log_formatter_uses_record_creation_time_for_timestamp() -> None:
    record = logging.makeLogRecord(
        {
            "name": "tailmate.runtime",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "gateway_request_completed",
        }
    )
    record.created = 1_711_800_000.5

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["timestamp"] == datetime.fromtimestamp(
        record.created,
        tz=timezone.utc,
    ).isoformat()


def test_generate_request_id_returns_non_empty_hex_token() -> None:
    request_id = generate_request_id()

    assert len(request_id) == 32
    assert int(request_id, 16) >= 0


def test_generate_trace_id_returns_non_empty_hex_token() -> None:
    trace_id = generate_trace_id()

    assert len(trace_id) == 32
    assert int(trace_id, 16) >= 0


def test_cloud_observability_emits_structured_trace_fields() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    runtime_logger = runtime_observability.logger
    original_handlers = list(runtime_logger.handlers)
    original_level = runtime_logger.level
    original_propagate = runtime_logger.propagate
    runtime_logger.handlers = [handler]
    runtime_logger.setLevel(logging.INFO)
    runtime_logger.propagate = False
    token = set_log_context(LogContext(trace_id="trace-123", user_id="user-123"))

    try:
        observability = runtime_observability.CloudObservability.__new__(
            runtime_observability.CloudObservability
        )
        observability.record_event("runtime_started", action="startup")
        observability.record_error("runtime_failed", action="shutdown")
    finally:
        reset_log_context(token)
        runtime_logger.handlers = original_handlers
        runtime_logger.setLevel(original_level)
        runtime_logger.propagate = original_propagate

    lines = [line for line in stream.getvalue().splitlines() if line.strip()]
    assert len(lines) == 2
    event_payload = json.loads(lines[0])
    error_payload = json.loads(lines[1])

    assert event_payload["message"] == "runtime_started"
    assert event_payload["trace_id"] == "trace-123"
    assert event_payload["user_id"] == "user-123"
    assert event_payload["action"] == "startup"
    assert error_payload["message"] == "runtime_failed"
    assert error_payload["trace_id"] == "trace-123"
    assert error_payload["user_id"] == "user-123"
    assert error_payload["action"] == "shutdown"
