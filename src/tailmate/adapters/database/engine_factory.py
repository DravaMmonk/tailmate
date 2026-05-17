"""Lazy database engine creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@dataclass(frozen=True)
class DatabaseEngineFactory:
    """Creates SQLAlchemy engines on demand for runtime use."""

    database_url: str
    connect_args: dict[str, Any] | None = None

    def create(self) -> Engine:
        # Keep engine construction stateless so local reloads do not retain
        # process-wide singleton connections across bootstrap cycles.
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if self.connect_args:
            kwargs["connect_args"] = self.connect_args
        return create_engine(self.database_url, **kwargs)
