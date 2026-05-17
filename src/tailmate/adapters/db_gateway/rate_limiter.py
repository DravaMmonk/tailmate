"""Public query sliding-window rate limiters for the gateway."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import math
from threading import Lock
from typing import Protocol

from sqlalchemy import delete, select, text

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import public_query_rate_limit_events
from tailmate.contracts.errors import DomainError
from tailmate.tracing import start_span


DEFAULT_PUBLIC_QUERY_RATE_LIMIT_REQUESTS = 30
DEFAULT_PUBLIC_QUERY_RATE_LIMIT_WINDOW_SECONDS = 60
POSTGRES_UNDEFINED_TABLE_SQLSTATE = "42P01"


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_user_id(user_id: str) -> str:
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        raise DomainError("user_id is required for rate limiting.")
    return normalized_user_id


def _coerce_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _retry_after_seconds(*, oldest_event_at: datetime, now: datetime, window_seconds: int) -> int:
    expires_at = _coerce_utc(oldest_event_at) + timedelta(seconds=window_seconds)
    remaining_seconds = (expires_at - now).total_seconds()
    return max(1, int(math.ceil(remaining_seconds)))


def _advisory_lock_key(user_id: str) -> int:
    digest = hashlib.sha256(user_id.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


def _extract_sqlstate(exc: BaseException) -> str | None:
    for candidate in (exc, getattr(exc, "orig", None)):
        if candidate is None:
            continue
        for attribute_name in ("sqlstate", "pgcode"):
            raw_value = getattr(candidate, attribute_name, None)
            if raw_value:
                return str(raw_value)
    return None


def _is_missing_public_query_rate_limit_table_error(exc: BaseException) -> bool:
    if _extract_sqlstate(exc) == POSTGRES_UNDEFINED_TABLE_SQLSTATE:
        return True

    for candidate in (exc, getattr(exc, "orig", None)):
        if candidate is None:
            continue
        message = str(candidate).lower()
        if (
            public_query_rate_limit_events.name in message
            and ("does not exist" in message or "no such table" in message)
        ):
            return True
    return False


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of evaluating the current user against the sliding window."""

    allowed: bool
    limit: int
    remaining: int
    window_seconds: int
    retry_after_seconds: int | None = None


class SlidingWindowRateLimiter(Protocol):
    """Shared contract for public-query rate limiting."""

    def check(self, *, user_id: str) -> RateLimitDecision: ...


@dataclass
class InMemorySlidingWindowRateLimiter:
    """Thread-safe in-memory sliding-window limiter used in tests and local fallbacks."""

    max_requests: int = DEFAULT_PUBLIC_QUERY_RATE_LIMIT_REQUESTS
    window_seconds: int = DEFAULT_PUBLIC_QUERY_RATE_LIMIT_WINDOW_SECONDS
    now_factory: Callable[[], datetime] = _utc_now
    _events: dict[str, deque[datetime]] = field(default_factory=dict, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def check(self, *, user_id: str) -> RateLimitDecision:
        normalized_user_id = _normalize_user_id(user_id)
        now = _coerce_utc(self.now_factory())
        window_start = now - timedelta(seconds=self.window_seconds)

        with self._lock:
            user_events = self._events.setdefault(normalized_user_id, deque())
            while user_events and _coerce_utc(user_events[0]) <= window_start:
                user_events.popleft()

            if len(user_events) >= self.max_requests:
                return RateLimitDecision(
                    allowed=False,
                    limit=self.max_requests,
                    remaining=0,
                    window_seconds=self.window_seconds,
                    retry_after_seconds=_retry_after_seconds(
                        oldest_event_at=user_events[0],
                        now=now,
                        window_seconds=self.window_seconds,
                    ),
                )

            user_events.append(now)
            return RateLimitDecision(
                allowed=True,
                limit=self.max_requests,
                remaining=max(self.max_requests - len(user_events), 0),
                window_seconds=self.window_seconds,
            )


@dataclass
class LocalFallbackSlidingWindowRateLimiter:
    """Fallback to an in-memory limiter in LOCAL when the rate-limit table is missing."""

    primary: SlidingWindowRateLimiter
    fallback: SlidingWindowRateLimiter
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _use_fallback_only: bool = field(default=False, init=False, repr=False)

    def check(self, *, user_id: str) -> RateLimitDecision:
        with self._lock:
            use_fallback_only = self._use_fallback_only

        if use_fallback_only:
            return self.fallback.check(user_id=user_id)

        try:
            return self.primary.check(user_id=user_id)
        except Exception as exc:
            if not _is_missing_public_query_rate_limit_table_error(exc):
                raise

            with self._lock:
                should_log_warning = not self._use_fallback_only
                self._use_fallback_only = True

            if should_log_warning:
                logger.warning(
                    "local_public_query_rate_limit_storage_missing",
                    extra={
                        "table_name": public_query_rate_limit_events.name,
                        "fallback": "in_memory",
                        "remediation": "Run `uv run alembic upgrade head` against the local gateway database.",
                    },
                )

            return self.fallback.check(user_id=user_id)


@dataclass(frozen=True)
class DatabaseSlidingWindowRateLimiter:
    """Database-backed sliding-window limiter for multi-instance public ingress."""

    engine_factory: DatabaseEngineFactory
    max_requests: int = DEFAULT_PUBLIC_QUERY_RATE_LIMIT_REQUESTS
    window_seconds: int = DEFAULT_PUBLIC_QUERY_RATE_LIMIT_WINDOW_SECONDS
    now_factory: Callable[[], datetime] = _utc_now

    def check(self, *, user_id: str) -> RateLimitDecision:
        normalized_user_id = _normalize_user_id(user_id)
        now = _coerce_utc(self.now_factory())
        window_start = now - timedelta(seconds=self.window_seconds)

        with start_span(
            "db.rate_limiter.check",
            attributes={"db.system": "postgresql", "db.operation": "select"},
        ):
            engine = self.engine_factory.create()
            try:
                with engine.begin() as connection:
                    if connection.dialect.name == "postgresql":
                        connection.execute(
                            text("SELECT pg_advisory_xact_lock(:lock_key)"),
                            {"lock_key": _advisory_lock_key(normalized_user_id)},
                        )

                    connection.execute(
                        delete(public_query_rate_limit_events).where(
                            public_query_rate_limit_events.c.user_id == normalized_user_id,
                            public_query_rate_limit_events.c.occurred_at < window_start,
                        )
                    )
                    recent_events = [
                        _coerce_utc(occurred_at)
                        for occurred_at in connection.execute(
                            select(public_query_rate_limit_events.c.occurred_at)
                            .where(
                                public_query_rate_limit_events.c.user_id == normalized_user_id,
                                public_query_rate_limit_events.c.occurred_at >= window_start,
                            )
                            .order_by(public_query_rate_limit_events.c.occurred_at.asc())
                        ).scalars()
                    ]
                    if len(recent_events) >= self.max_requests:
                        return RateLimitDecision(
                            allowed=False,
                            limit=self.max_requests,
                            remaining=0,
                            window_seconds=self.window_seconds,
                            retry_after_seconds=_retry_after_seconds(
                                oldest_event_at=recent_events[0],
                                now=now,
                                window_seconds=self.window_seconds,
                            ),
                        )

                    connection.execute(
                        public_query_rate_limit_events.insert().values(
                            user_id=normalized_user_id,
                            occurred_at=now,
                        )
                    )
                    return RateLimitDecision(
                        allowed=True,
                        limit=self.max_requests,
                        remaining=max(self.max_requests - len(recent_events) - 1, 0),
                        window_seconds=self.window_seconds,
                    )
            finally:
                engine.dispose()
