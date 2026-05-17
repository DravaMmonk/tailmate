"""Abstract observability contract."""

from __future__ import annotations

from typing import Any, Protocol


class Observability(Protocol):
    """Logging and tracing boundary."""

    def info(self, message: str, **fields: Any) -> None: ...

    def error(self, message: str, **fields: Any) -> None: ...
