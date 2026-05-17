"""Cloud runtime observability adapter."""

from __future__ import annotations

import logging
from typing import Any

from tailmate.observability import configure_structured_logging
from tailmate.tracing import configure_tracing
from tailmate.bootstrap.config import AppEnvironment


logger = logging.getLogger("tailmate.runtime")


class CloudObservability:
    """Structured logging boundary for runtime integration."""

    def __init__(self, *, environment: AppEnvironment | None = None) -> None:
        configure_structured_logging()
        configure_tracing(
            environment=environment,
            service_name="tailmate-vertex-runtime",
        )

    def record_event(self, message: str, **fields: Any) -> None:
        logger.info(message, extra=fields)

    def record_error(self, message: str, **fields: Any) -> None:
        logger.error(message, extra=fields)

    def info(self, message: str, **fields: Any) -> None:
        self.record_event(message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self.record_error(message, **fields)
