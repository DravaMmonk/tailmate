"""Interactive local chat entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TextIO
from uuid import uuid4

from tailmate.adapters.vertex_agent_engine.agent_app import create_agent_app
from tailmate.bootstrap.config import AppEnvironment
from tailmate.contracts.constants import DOG_PROFILE_RESULT_METADATA_KEY, TURN_DEBUG_METADATA_KEY
from tailmate.entrypoints.local_env import ensure_local_environment, ensure_local_user_exists


def add_local_chat_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the interactive `local-chat` command."""

    parser = subparsers.add_parser(
        "local-chat",
        help="Run the local agent in an interactive multi-turn REPL.",
    )
    parser.add_argument(
        "--dog-id",
        help="Existing dog identifier to bind to the local chat session.",
    )
    parser.add_argument(
        "--session-id",
        help="Optional session id. Defaults to a generated local-chat session id.",
    )
    parser.add_argument(
        "--user-id",
        help="Optional trusted user id to attach to owner-scoped dog-profile turns.",
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Hide the compact metadata summary after each assistant turn.",
    )
    parser.set_defaults(func=run_local_chat)


def build_local_chat_summary(response: dict[str, object]) -> dict[str, object]:
    """Build the compact debug payload required by the issue."""

    metadata = response.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    turn_debug = metadata.get(TURN_DEBUG_METADATA_KEY, {})
    if not isinstance(turn_debug, dict):
        turn_debug = {}
    dog_profile_result = metadata.get(DOG_PROFILE_RESULT_METADATA_KEY, {})
    if not isinstance(dog_profile_result, dict):
        dog_profile_result = {}
    skill_attempted = turn_debug.get("skill_attempted", [])
    if not isinstance(skill_attempted, list):
        skill_attempted = []
    return {
        "skill_attempted": skill_attempted,
        "fallback_reason": turn_debug.get("fallback_reason"),
        "dog_profile_action": dog_profile_result.get("action"),
        "turn_count": metadata.get("turn_count"),
    }


def emit_local_chat_response(
    response: dict[str, object],
    *,
    output: TextIO,
    include_debug: bool,
) -> str | None:
    """Print the assistant response and optional debug summary."""

    error = response.get("error")
    if isinstance(error, dict):
        error_type = str(error.get("type", "internal_error"))
        error_message = str(error.get("message", "An unexpected internal error occurred."))
        print(f"Error [{error_type}]: {error_message}", file=output)
    else:
        print(str(response.get("response", "")), file=output)

    metadata = response.get("metadata", {})
    resolved_dog_id = None
    if isinstance(metadata, dict):
        candidate = metadata.get("dog_id")
        if candidate is not None and str(candidate).strip():
            resolved_dog_id = str(candidate).strip()

    if include_debug:
        print(
            json.dumps(
                build_local_chat_summary(response),
                ensure_ascii=False,
            ),
            file=output,
        )
    return resolved_dog_id


def run_local_chat(
    args: argparse.Namespace,
    *,
    input_func=input,
    output: TextIO = sys.stdout,
) -> int:
    """Run an interactive local REPL against the local agent."""

    config = ensure_local_environment()
    trusted_user_id = str(getattr(args, "user_id", "") or "").strip()
    if trusted_user_id:
        ensure_local_user_exists(config, trusted_user_id)
    agent = create_agent_app(environment=AppEnvironment.LOCAL)
    agent.set_up()

    session_id = args.session_id or f"local-chat-{uuid4()}"
    active_dog_id = args.dog_id

    print(f"Session: {session_id}", file=output)
    try:
        while True:
            try:
                user_message = input_func("> ")
            except EOFError:
                print("Stopping local chat.", file=output)
                return 0

            normalized_message = user_message.strip()
            if not normalized_message:
                continue
            if normalized_message.lower() in {"exit", "quit"}:
                print("Stopping local chat.", file=output)
                return 0

            metadata: dict[str, object] = {}
            if active_dog_id:
                metadata["dog_id"] = active_dog_id
            if trusted_user_id:
                metadata["user_id"] = trusted_user_id

            response = agent.query(
                session_id=session_id,
                message=user_message,
                metadata=metadata,
            )
            resolved_dog_id = emit_local_chat_response(
                response,
                output=output,
                include_debug=not args.no_debug,
            )
            if resolved_dog_id:
                active_dog_id = resolved_dog_id
    except KeyboardInterrupt:
        print("\nStopping local chat.", file=output)
        return 0
