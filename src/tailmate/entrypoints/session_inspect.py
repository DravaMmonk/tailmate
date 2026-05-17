"""Session inspection entrypoint."""

from __future__ import annotations

import argparse
import json
import sys

from tailmate.adapters.database.conversation_store import DatabaseConversationStore
from tailmate.agent_runtime.models.session_context import SessionContext
from tailmate.entrypoints.local_env import build_local_container


def add_session_inspect_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Register the `session inspect` command."""

    parser = subparsers.add_parser(
        "inspect",
        help="Pretty-print a persisted conversation session as JSON.",
    )
    parser.add_argument("session_id", help="Conversation session identifier to inspect.")
    parser.set_defaults(func=run_session_inspect)


def serialize_session_context(context: SessionContext) -> dict[str, object]:
    """Convert the session context into a JSON-serializable structure."""

    return {
        "session_id": context.session_id,
        "turns": context.turns,
        "attributes": context.attributes,
    }


def build_local_conversation_store() -> DatabaseConversationStore:
    """Build the direct database conversation store for local developer commands."""

    container = build_local_container()
    return DatabaseConversationStore(engine_factory=container.build_engine_factory())


def run_session_inspect(args: argparse.Namespace) -> int:
    """Print the stored session state for the requested session id."""

    store = build_local_conversation_store()
    context = store.load_optional(args.session_id)
    if context is None:
        print(f"Session '{args.session_id}' does not exist.", file=sys.stderr)
        return 1

    json.dump(serialize_session_context(context), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0
