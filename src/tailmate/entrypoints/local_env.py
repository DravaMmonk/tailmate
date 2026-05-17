"""Shared local-environment helpers for developer entrypoints."""

from __future__ import annotations

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import socket

import google.auth
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request
from dotenv import load_dotenv
from sqlalchemy import text

from tailmate.bootstrap.config import AppConfig, AppEnvironment, ExtractionStrategy


@dataclass(frozen=True)
class EnvironmentCheckResult:
    """One local-environment validation outcome."""

    name: str
    passed: bool
    message: str
    remediation: str | None = None


def ensure_local_environment() -> AppConfig:
    """Load local configuration and validate the sandbox contract."""

    config = load_local_config()
    check_environment(config)
    return config


def load_local_config() -> AppConfig:
    """Load local config after enforcing the explicit `.env` contract."""

    load_dotenv()
    os.environ["TAILMATE_ENV"] = AppEnvironment.LOCAL.value
    env_file = require_local_env_file()
    require_explicit_local_env_marker(env_file)
    return AppConfig.from_env()


def strategy_requires_vertex_ai_adc(config: AppConfig) -> bool:
    """Return whether the configured extractor must reach Gemini through ADC."""

    return config.extraction_strategy in {
        ExtractionStrategy.FLASH,
        ExtractionStrategy.PRO,
    }


def validate_vertex_ai_adc() -> None:
    """Ensure Vertex AI ADC is available for strategies that require live Gemini access."""

    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except DefaultCredentialsError as exc:
        raise RuntimeError(
            "The configured extraction strategy requires Vertex AI ADC. "
            "Run `gcloud auth application-default login` before starting local development."
        ) from exc
    try:
        credentials.refresh(Request())
    except Exception as exc:
        raise RuntimeError(
            "Vertex AI ADC could not be refreshed for local development. "
            "Run `gcloud auth application-default login` again and retry."
        ) from exc


def require_local_env_file() -> Path:
    """Require the repository-local `.env` file used by developer workflows."""

    env_file = Path(".env")
    if not env_file.is_file():
        raise RuntimeError("Local development requires a .env file in the repository root.")
    return env_file


def require_explicit_local_env_marker(env_file: Path) -> None:
    """Require `.env` to opt into local mode explicitly."""

    env_text = env_file.read_text(encoding="utf-8")
    if "TAILMATE_ENV=LOCAL" not in env_text:
        raise RuntimeError("Local development requires .env to declare TAILMATE_ENV=LOCAL explicitly.")


def validate_database_proxy(config: AppConfig) -> None:
    """Ensure the local database proxy is reachable before agent startup."""

    try:
        with socket.create_connection(
            (config.local_tunnel_host, config.local_tunnel_port),
            timeout=1,
        ):
            pass
    except OSError as exc:
        raise RuntimeError(
            "Database proxy is not reachable at "
            f"{config.local_tunnel_host}:{config.local_tunnel_port}. "
            "Start the local database proxy first, for example ./scripts/start_cloudsql_proxy.sh."
        ) from exc


def build_alembic_config() -> AlembicConfig:
    """Build the repository-local Alembic config used for local schema sync."""

    repo_root = Path(__file__).resolve().parents[3]
    return AlembicConfig(str(repo_root / "alembic.ini"))


@contextmanager
def override_alembic_database_url(database_url: str):
    """Temporarily force Alembic to target the current local preflight database."""

    original_url = os.environ.get("TAILMATE_ALEMBIC_DATABASE_URL")
    os.environ["TAILMATE_ALEMBIC_DATABASE_URL"] = database_url
    try:
        yield
    finally:
        if original_url is None:
            os.environ.pop("TAILMATE_ALEMBIC_DATABASE_URL", None)
        else:
            os.environ["TAILMATE_ALEMBIC_DATABASE_URL"] = original_url


def _load_current_schema_heads(config: AppConfig) -> tuple[str, ...]:
    """Load the currently applied Alembic heads from the local test database."""

    from tailmate.bootstrap.container import AppContainer

    engine = AppContainer(config=config).build_engine_factory().create()
    try:
        with engine.begin() as connection:
            version_rows = connection.execute(
                text("SELECT version_num FROM alembic_version ORDER BY version_num")
            ).scalars()
            return tuple(str(version) for version in version_rows)
    except Exception:
        return ()
    finally:
        engine.dispose()


def reset_local_database_schema(config: AppConfig) -> None:
    """Reset the local PostgreSQL test schema when migration drift is detected."""

    from tailmate.bootstrap.container import AppContainer

    engine = AppContainer(config=config).build_engine_factory().create()
    try:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
            connection.execute(text("GRANT ALL ON SCHEMA public TO CURRENT_USER"))
            connection.execute(text("GRANT ALL ON SCHEMA public TO PUBLIC"))
    finally:
        engine.dispose()


def sync_local_database_schema(config: AppConfig) -> str:
    """Reset and upgrade the local test database when its schema drifts."""

    from tailmate.bootstrap.container import AppContainer

    alembic_config = build_alembic_config()
    expected_heads = tuple(sorted(ScriptDirectory.from_config(alembic_config).get_heads()))
    current_heads = tuple(sorted(_load_current_schema_heads(config)))
    if current_heads == expected_heads and current_heads:
        return "Local test database schema already matches the current migration heads."

    local_database_url = AppContainer(config=config).build_database_url()
    reset_local_database_schema(config)
    with override_alembic_database_url(local_database_url):
        command.upgrade(alembic_config, "heads")
    return "Local test database schema was reset and synchronized to the current migration heads."


def _load_table_column_names(connection, table_name: str) -> set[str]:
    """Return the column names for one public table."""

    rows = connection.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).scalars()
    return {str(column_name) for column_name in rows}


def ensure_local_user_exists(config: AppConfig, user_id: str) -> None:
    """Ensure a trusted local test user exists for owner-scoped flows."""

    normalized_user_id = str(user_id).strip()
    if not normalized_user_id:
        return

    from tailmate.bootstrap.container import AppContainer

    engine = AppContainer(config=config).build_engine_factory().create()
    try:
        with engine.begin() as connection:
            user_columns = _load_table_column_names(connection, "users")
            if not user_columns:
                return

            if {"platform", "platform_user_id"}.issubset(user_columns):
                connection.execute(
                    text(
                        """
                        INSERT INTO users (user_id, platform, platform_user_id, status, role)
                        VALUES (:user_id, :platform, :platform_user_id, :status, :role)
                        ON CONFLICT (user_id) DO UPDATE
                        SET platform = EXCLUDED.platform,
                            platform_user_id = EXCLUDED.platform_user_id,
                            status = EXCLUDED.status,
                            role = EXCLUDED.role
                        """
                    ),
                    {
                        "user_id": normalized_user_id,
                        "platform": "web",
                        "platform_user_id": normalized_user_id,
                        "status": "active",
                        "role": "owner",
                    },
                )
            else:
                connection.execute(
                    text(
                        """
                        INSERT INTO users (user_id, status, role)
                        VALUES (:user_id, :status, :role)
                        ON CONFLICT (user_id) DO UPDATE
                        SET status = EXCLUDED.status,
                            role = EXCLUDED.role
                        """
                    ),
                    {
                        "user_id": normalized_user_id,
                        "status": "active",
                        "role": "owner",
                    },
                )

            connection_columns = _load_table_column_names(connection, "user_platform_connections")
            if connection_columns:
                connection.execute(
                    text(
                        """
                        INSERT INTO user_platform_connections
                            (user_id, platform, platform_user_id, status, disconnected_at)
                        VALUES
                            (:user_id, :platform, :platform_user_id, :status, NULL)
                        ON CONFLICT (user_id, platform) DO UPDATE
                        SET platform_user_id = EXCLUDED.platform_user_id,
                            status = EXCLUDED.status,
                            disconnected_at = NULL
                        """
                    ),
                    {
                        "user_id": normalized_user_id,
                        "platform": "web",
                        "platform_user_id": normalized_user_id,
                        "status": "active",
                    },
                )
    finally:
        engine.dispose()


def collect_environment_check_results() -> list[EnvironmentCheckResult]:
    """Run local pre-flight checks and return the ordered diagnostic results."""

    load_dotenv()
    os.environ["TAILMATE_ENV"] = AppEnvironment.LOCAL.value

    results: list[EnvironmentCheckResult] = []
    env_file = Path(".env")
    if not env_file.is_file():
        results.append(
            EnvironmentCheckResult(
                name=".env file",
                passed=False,
                message="Local development requires a .env file in the repository root.",
                remediation="Create a repository-root `.env` file before running local CLI commands.",
            )
        )
        return results

    results.append(
        EnvironmentCheckResult(
            name=".env file",
            passed=True,
            message="Found .env in the repository root.",
        )
    )

    env_text = env_file.read_text(encoding="utf-8")
    if "TAILMATE_ENV=LOCAL" not in env_text:
        results.append(
            EnvironmentCheckResult(
                name="TAILMATE_ENV marker",
                passed=False,
                message="Local development requires .env to declare TAILMATE_ENV=LOCAL explicitly.",
                remediation="Add `TAILMATE_ENV=LOCAL` to `.env` and retry.",
            )
        )
        return results

    results.append(
        EnvironmentCheckResult(
            name="TAILMATE_ENV marker",
            passed=True,
            message=".env declares TAILMATE_ENV=LOCAL.",
        )
    )

    try:
        config = AppConfig.from_env()
    except Exception as exc:
        results.append(
            EnvironmentCheckResult(
                name="Local configuration",
                passed=False,
                message=str(exc),
                remediation="Populate the required `TAILMATE_*` variables in `.env` before retrying.",
            )
        )
        return results

    try:
        validate_database_proxy(config)
    except RuntimeError as exc:
        results.append(
            EnvironmentCheckResult(
                name="Database proxy",
                passed=False,
                message=str(exc),
                remediation="Start the Cloud SQL proxy and confirm the configured host/port are reachable.",
            )
        )
        return results

    results.append(
        EnvironmentCheckResult(
            name="Database proxy",
            passed=True,
            message=(
                f"Database proxy is reachable at {config.local_tunnel_host}:{config.local_tunnel_port}."
            ),
        )
    )

    try:
        schema_message = sync_local_database_schema(config)
    except Exception as exc:
        results.append(
            EnvironmentCheckResult(
                name="Database schema",
                passed=False,
                message=str(exc),
                remediation=(
                    "Clear the local test database or fix the migration graph, "
                    "then rerun the command."
                ),
            )
        )
        return results

    results.append(
        EnvironmentCheckResult(
            name="Database schema",
            passed=True,
            message=schema_message,
        )
    )

    if not strategy_requires_vertex_ai_adc(config):
        results.append(
            EnvironmentCheckResult(
                name="Vertex AI ADC",
                passed=True,
                message=(
                    "ADC is optional for the "
                    f"`{config.extraction_strategy.value}` extraction strategy."
                ),
            )
        )
        return results

    try:
        validate_vertex_ai_adc()
    except RuntimeError as exc:
        results.append(
            EnvironmentCheckResult(
                name="Vertex AI ADC",
                passed=False,
                message=str(exc),
                remediation="Run `gcloud auth application-default login` and retry the command.",
            )
        )
        return results

    results.append(
        EnvironmentCheckResult(
            name="Vertex AI ADC",
            passed=True,
            message="ADC credentials loaded and refreshed successfully.",
        )
    )
    return results


def check_environment(config: AppConfig) -> None:
    """Fail fast when the local sandbox prerequisites are missing."""

    env_file = require_local_env_file()
    require_explicit_local_env_marker(env_file)
    validate_database_proxy(config)
    sync_local_database_schema(config)

    if strategy_requires_vertex_ai_adc(config):
        validate_vertex_ai_adc()


def build_local_container():
    """Build the local dependency container after completing pre-flight checks."""

    from tailmate.bootstrap.container import AppContainer

    return AppContainer(config=ensure_local_environment())
