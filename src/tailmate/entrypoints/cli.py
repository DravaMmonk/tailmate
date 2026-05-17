"""Developer CLI entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from tailmate.entrypoints.env_check import add_env_check_parser
from tailmate.entrypoints.local_chat import add_local_chat_parser
from tailmate.entrypoints.local_demo import add_local_demo_parser
from tailmate.entrypoints.kb import add_kb_parser
from tailmate.entrypoints.new_skill import (
    build_skill_scaffold_context,
    create_new_skill_scaffold,
    render_new_skill_next_steps,
)
from tailmate.entrypoints.session_delete import add_session_delete_parser
from tailmate.entrypoints.session_inspect import add_session_inspect_parser
from tailmate.entrypoints.skill_list import add_skill_list_parser


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level developer CLI parser."""

    parser = argparse.ArgumentParser(prog="tailmate")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_skill_parser = subparsers.add_parser(
        "new-skill",
        help="Generate a new vertical-slice skill scaffold.",
    )
    new_skill_parser.add_argument("name", help="Skill id in snake_case.")
    new_skill_parser.set_defaults(func=run_new_skill)

    add_env_check_parser(subparsers)
    add_local_chat_parser(subparsers)
    add_local_demo_parser(subparsers)
    add_kb_parser(subparsers)

    session_parser = subparsers.add_parser(
        "session",
        help="Inspect or delete persisted conversation sessions.",
    )
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)
    add_session_inspect_parser(session_subparsers)
    add_session_delete_parser(session_subparsers)

    skill_parser = subparsers.add_parser(
        "skill",
        help="Inspect the resolved local skill inventory.",
    )
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)
    add_skill_list_parser(skill_subparsers)
    return parser


def run_new_skill(args: argparse.Namespace) -> int:
    """Generate a scaffold for a new skill."""

    context = build_skill_scaffold_context(args.name)
    created_paths = create_new_skill_scaffold(args.name)
    for path in created_paths:
        print(path)
    print()
    print(render_new_skill_next_steps(context))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for repository-local developer workflows."""

    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
