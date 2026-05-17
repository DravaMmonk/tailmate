"""Session deletion entrypoint."""

from __future__ import annotations

import argparse
import sys

from tailmate.entrypoints.session_inspect import build_local_conversation_store


def add_session_delete_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the `session delete` command."""

    parser = subparsers.add_parser(
        "delete",
        help="Delete a persisted conversation session.",
    )
    parser.add_argument("session_id", help="Conversation session identifier to delete.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm the destructive delete operation.",
    )
    parser.set_defaults(func=run_session_delete)


def run_session_delete(args: argparse.Namespace) -> int:
    """Delete the requested session after an explicit confirmation flag."""

    if not args.yes:
        print("Refusing to delete a session without --yes.", file=sys.stderr)
        return 1

    store = build_local_conversation_store()
    deleted = store.delete(args.session_id)
    if not deleted:
        print(f"Session '{args.session_id}' does not exist.", file=sys.stderr)
        return 1

    print(f"Deleted session '{args.session_id}'.")
    return 0
