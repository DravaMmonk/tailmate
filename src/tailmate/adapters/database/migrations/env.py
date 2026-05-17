"""Alembic environment configuration."""
# ruff: noqa: E402

from __future__ import annotations

import os
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import create_engine, pool

PROJECT_SRC = Path(__file__).resolve().parents[4]
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))

from tailmate.adapters.database.models import metadata
from tailmate.bootstrap.config import AppConfig
from tailmate.bootstrap.container import AppContainer


config = getattr(context, "config", None)
target_metadata = metadata


def build_runtime_database_url() -> str:
    """Build the database URL from the canonical application container."""

    explicit_url = os.getenv("TAILMATE_ALEMBIC_DATABASE_URL")
    if explicit_url:
        return explicit_url
    app_config = AppConfig.from_env()
    return AppContainer(config=app_config).build_database_url()


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""

    url = build_runtime_database_url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""

    connectable = create_engine(
        build_runtime_database_url(),
        poolclass=pool.NullPool,
        pool_pre_ping=True,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if config is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
