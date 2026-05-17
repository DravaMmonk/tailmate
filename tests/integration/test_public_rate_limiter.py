from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, select

from tailmate.adapters.database.engine_factory import DatabaseEngineFactory
from tailmate.adapters.database.models import metadata, public_query_rate_limit_events
from tailmate.adapters.db_gateway.rate_limiter import (
    DatabaseSlidingWindowRateLimiter,
    InMemorySlidingWindowRateLimiter,
    LocalFallbackSlidingWindowRateLimiter,
)


def test_database_public_query_rate_limiter_enforces_sliding_window(tmp_path: Path) -> None:
    database_path = tmp_path / "rate-limit.sqlite3"
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    metadata.create_all(engine, tables=[public_query_rate_limit_events])
    engine.dispose()

    current_time = datetime(2026, 3, 29, tzinfo=timezone.utc)
    limiter = DatabaseSlidingWindowRateLimiter(
        engine_factory=DatabaseEngineFactory(f"sqlite+pysqlite:///{database_path}"),
        max_requests=2,
        window_seconds=60,
        now_factory=lambda: current_time,
    )

    first = limiter.check(user_id="user-1")
    second = limiter.check(user_id="user-1")
    third = limiter.check(user_id="user-1")

    assert first.allowed is True
    assert first.remaining == 1
    assert second.allowed is True
    assert second.remaining == 0
    assert third.allowed is False
    assert third.retry_after_seconds == 60

    current_time = current_time + timedelta(seconds=61)
    fourth = limiter.check(user_id="user-1")

    assert fourth.allowed is True
    assert fourth.remaining == 1

    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    with engine.begin() as connection:
        events = connection.execute(
            select(
                public_query_rate_limit_events.c.user_id,
                public_query_rate_limit_events.c.occurred_at,
            ).order_by(public_query_rate_limit_events.c.id.asc())
        ).all()
    engine.dispose()

    assert len(events) == 1
    assert events[0][0] == "user-1"


def test_local_rate_limiter_falls_back_to_memory_when_storage_table_is_missing(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "rate-limit-missing-table.sqlite3"
    current_time = datetime(2026, 3, 29, tzinfo=timezone.utc)
    engine_factory = DatabaseEngineFactory(f"sqlite+pysqlite:///{database_path}")

    limiter = LocalFallbackSlidingWindowRateLimiter(
        primary=DatabaseSlidingWindowRateLimiter(
            engine_factory=engine_factory,
            max_requests=2,
            window_seconds=60,
            now_factory=lambda: current_time,
        ),
        fallback=InMemorySlidingWindowRateLimiter(
            max_requests=2,
            window_seconds=60,
            now_factory=lambda: current_time,
        ),
    )

    first = limiter.check(user_id="user-1")
    second = limiter.check(user_id="user-1")
    third = limiter.check(user_id="user-1")

    assert first.allowed is True
    assert first.remaining == 1
    assert second.allowed is True
    assert second.remaining == 0
    assert third.allowed is False
    assert third.retry_after_seconds == 60

    current_time = current_time + timedelta(seconds=61)
    fourth = limiter.check(user_id="user-1")

    assert fourth.allowed is True
    assert fourth.remaining == 1
