"""Abstract transient memory contract."""

from __future__ import annotations

from typing import Any, Protocol


class MemoryStore(Protocol):
    """Optional non-SSOT memory interface."""

    def read(self, key: str) -> Any: ...

    def write(self, key: str, value: Any) -> None: ...
