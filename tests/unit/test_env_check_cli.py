from __future__ import annotations

import argparse
import importlib


def test_build_parser_registers_env_check(monkeypatch) -> None:
    module = importlib.import_module("tailmate.entrypoints.cli")

    args = module.build_parser().parse_args(["env-check"])

    assert args.command == "env-check"
    assert args.func.__name__ == "run_env_check"


def test_run_env_check_prints_pass_summary(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.env_check")
    local_env = importlib.import_module("tailmate.entrypoints.local_env")
    monkeypatch.setattr(
        local_env,
        "collect_environment_check_results",
        lambda: [
            local_env.EnvironmentCheckResult(
                name=".env file",
                passed=True,
                message="Found .env in the repository root.",
            ),
            local_env.EnvironmentCheckResult(
                name="Database proxy",
                passed=True,
                message="Database proxy is reachable at 127.0.0.1:5432.",
            ),
        ],
    )

    exit_code = module.run_env_check(argparse.Namespace())

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[PASS] .env file: Found .env in the repository root." in captured.out
    assert "[PASS] Database proxy: Database proxy is reachable at 127.0.0.1:5432." in captured.out


def test_run_env_check_prints_failure_hint(monkeypatch, capsys) -> None:
    module = importlib.import_module("tailmate.entrypoints.env_check")
    local_env = importlib.import_module("tailmate.entrypoints.local_env")
    monkeypatch.setattr(
        local_env,
        "collect_environment_check_results",
        lambda: [
            local_env.EnvironmentCheckResult(
                name="Vertex AI ADC",
                passed=False,
                message="The configured extraction strategy requires Vertex AI ADC.",
                remediation="Run `gcloud auth application-default login` and retry the command.",
            )
        ],
    )

    exit_code = module.run_env_check(argparse.Namespace())

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "[FAIL] Vertex AI ADC: The configured extraction strategy requires Vertex AI ADC." in captured.out
    assert "Hint: Run `gcloud auth application-default login` and retry the command." in captured.out


def test_collect_environment_check_results_marks_optional_adc(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("TAILMATE_ENV=LOCAL\n", encoding="utf-8")
    monkeypatch.setenv("TAILMATE_PROJECT_ID", "test-project")
    monkeypatch.setenv("TAILMATE_LOCATION", "us-central1")
    monkeypatch.setenv("TAILMATE_DB_USER", "user")
    monkeypatch.setenv("TAILMATE_DB_PASSWORD", "pass")
    monkeypatch.setenv("TAILMATE_DB_IP", "10.0.0.10")
    monkeypatch.setenv("TAILMATE_DB_NAME", "postgres")
    monkeypatch.setenv("TAILMATE_LOCAL_TUNNEL_HOST", "127.0.0.1")
    monkeypatch.setenv("TAILMATE_LOCAL_TUNNEL_PORT", "5432")
    monkeypatch.setenv("TAILMATE_EXTRACTION_STRATEGY", "composite")
    module = importlib.import_module("tailmate.entrypoints.local_env")

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(module.socket, "create_connection", lambda address, timeout: FakeSocket())
    monkeypatch.setattr(
        module,
        "sync_local_database_schema",
        lambda config: "Local test database schema was reset and synchronized to the current migration heads.",
    )

    results = module.collect_environment_check_results()

    assert [result.name for result in results] == [
        ".env file",
        "TAILMATE_ENV marker",
        "Database proxy",
        "Database schema",
        "Vertex AI ADC",
    ]
    assert all(result.passed for result in results)
    assert (
        results[3].message
        == "Local test database schema was reset and synchronized to the current migration heads."
    )
    assert results[-1].message == "ADC is optional for the `composite` extraction strategy."


def test_collect_environment_check_results_stops_at_env_file_failure(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module("tailmate.entrypoints.local_env")

    results = module.collect_environment_check_results()

    assert len(results) == 1
    assert results[0].name == ".env file"
    assert results[0].passed is False
