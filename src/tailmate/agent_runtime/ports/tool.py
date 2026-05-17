"""Abstract tool contract."""

from __future__ import annotations

from typing import Any, Protocol


class Tool(Protocol):
    """Narrow callable tool interface."""

    name: str

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]: ...
