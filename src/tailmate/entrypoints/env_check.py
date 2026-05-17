"""Dedicated environment diagnostics entrypoint."""

from __future__ import annotations

import argparse

def add_env_check_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the `env-check` command on the developer CLI."""

    parser = subparsers.add_parser(
        "env-check",
        help="Validate the local development environment contract.",
    )
    parser.set_defaults(func=run_env_check)


def run_env_check(args: argparse.Namespace) -> int:
    """Print a pass/fail summary for the local pre-flight checks."""

    del args
    from tailmate.entrypoints.local_env import collect_environment_check_results

    results = collect_environment_check_results()
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"[{status}] {result.name}: {result.message}")
        if not result.passed:
            if result.remediation:
                print(f"Hint: {result.remediation}")
            return 1
    return 0
