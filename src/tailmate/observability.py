"""Structured logging helpers shared across Tailmate services."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import json
import logging
from typing import Any
from uuid import uuid4

from tailmate.tracing import current_trace_fields


STANDARD_LOG_RECORD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__.keys())


@dataclass(slots=True)
class LogContext:
    """Request-scoped structured logging fields."""

    request_id: str | None = None
    trace_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    skill: str | None = None
    intent: str | None = None


_current_log_context: ContextVar[LogContext] = ContextVar(
    "tailmate_log_context",
    default=LogContext(),
)


def generate_request_id() -> str:
    """Return a new correlation id for the current request."""

    return uuid4().hex


def generate_trace_id() -> str:
    """Return a new correlation id for trace-level request stitching."""

    return uuid4().hex


def set_log_context(context: LogContext) -> Token[LogContext]:
    """Install a new request-scoped logging context."""

    return _current_log_context.set(context)


def reset_log_context(token: Token[LogContext]) -> None:
    """Restore the previous logging context."""

    _current_log_context.reset(token)


def get_log_context() -> LogContext:
    """Return the active logging context."""

    return _current_log_context.get()


def update_log_context(**fields: str | None) -> None:
    """Merge non-empty fields into the active logging context."""

    current = get_log_context()
    normalized_fields = {
        key: value.strip() if isinstance(value, str) else value
        for key, value in fields.items()
        if value is not None
    }
    _current_log_context.set(replace(current, **normalized_fields))


def _normalize_log_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _normalize_log_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [_normalize_log_value(item) for item in value]
    return str(value)


class JsonLogFormatter(logging.Formatter):
    """Render log records as a single-line JSON payload."""

    def format(self, record: logging.LogRecord) -> str:
        context = asdict(get_log_context())
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": record.getMessage(),
            "message": record.getMessage(),
            **{key: value for key, value in context.items() if value},
            **current_trace_fields(),
        }
        extra_fields = {
            key: _normalize_log_value(value)
            for key, value in record.__dict__.items()
            if key not in STANDARD_LOG_RECORD_FIELDS and not key.startswith("_")
        }
        if "skill" not in extra_fields and "skill_id" in extra_fields:
            extra_fields["skill"] = extra_fields["skill_id"]
        if "latency_ms" not in extra_fields and "duration_ms" in extra_fields:
            extra_fields["latency_ms"] = extra_fields["duration_ms"]
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        payload.update(
            {
                key: value
                for key, value in extra_fields.items()
                if value is not None
            }
        )
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_structured_logging(level: int = logging.INFO) -> None:
    """Configure the root logger to emit JSON-formatted structured logs."""

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.addHandler(logging.StreamHandler())
    root_logger.setLevel(level)
    formatter = JsonLogFormatter()
    for handler in root_logger.handlers:
        if getattr(handler, "_tailmate_structured_logging", False):
            continue
        handler.setFormatter(formatter)
        handler._tailmate_structured_logging = True
