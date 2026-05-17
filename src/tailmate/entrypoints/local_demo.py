"""Local product demo entrypoint."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
from pathlib import Path
import sys
from uuid import uuid4

from tailmate.adapters.vertex_agent_engine.agent_app import create_agent_app
from tailmate.bootstrap.config import AppEnvironment
from tailmate.contracts.constants import STRIP_METADATA_REQUEST_METADATA_KEY


DEFAULT_STRIP_METADATA_MESSAGE = "sanitize this upload"


def add_local_demo_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the local demo command on the shared developer CLI."""

    parser = subparsers.add_parser(
        "local-demo",
        help="Run the local agent against a text query or media file.",
    )
    parser.add_argument("--message", help="Text message to send to the local agent.")
    parser.add_argument(
        "--file",
        help="Optional media file to run through the strip_metadata product path.",
    )
    parser.add_argument(
        "--dog-id",
        help="Existing dog identifier to attach to the local request. Omit it to let dog_profile create from the message.",
    )
    parser.add_argument(
        "--user-id",
        help="Optional trusted user id to attach to owner-scoped requests.",
    )
    parser.add_argument(
        "--session-id",
        help="Optional session id. Defaults to a generated local-demo session id.",
    )
    parser.add_argument(
        "--resource-kind",
        help="Storage segment for media uploads. Defaults to images/videos from content type.",
    )
    parser.add_argument(
        "--content-type",
        help="Explicit media content type. Defaults from file extension when possible.",
    )
    parser.set_defaults(func=run_local_demo)


def build_local_demo_query(args: argparse.Namespace) -> dict[str, object]:
    """Build the local query payload from CLI arguments."""

    session_id = args.session_id or f"local-demo-{uuid4()}"
    metadata: dict[str, object] = {}
    if args.dog_id:
        metadata["dog_id"] = args.dog_id
    user_id = str(getattr(args, "user_id", "") or "").strip()
    message = args.message or ""
    if user_id:
        metadata["user_id"] = user_id

    if args.file:
        if not args.dog_id:
            raise ValueError("--dog-id is required when --file is provided.")
        media_path = Path(args.file).expanduser().resolve()
        if not media_path.is_file():
            raise ValueError(f"--file does not point to a file: {media_path}")

        content_type = (
            args.content_type
            or mimetypes.guess_type(media_path.name)[0]
            or "application/octet-stream"
        )
        resource_kind = args.resource_kind
        if not resource_kind:
            if content_type.startswith("audio/"):
                resource_kind = "audio"
            elif content_type.startswith("video/"):
                resource_kind = "videos"
            else:
                resource_kind = "images"

        metadata[STRIP_METADATA_REQUEST_METADATA_KEY] = {
            "dog_id": args.dog_id,
            "resource_kind": resource_kind,
            "filename": media_path.name,
            "content_type": content_type,
            "payload_base64": base64.b64encode(media_path.read_bytes()).decode("ascii"),
        }
        if not message:
            message = DEFAULT_STRIP_METADATA_MESSAGE

    if not message:
        raise ValueError("Provide either --message or --file.")

    return {
        "session_id": session_id,
        "message": message,
        "metadata": metadata,
    }


def run_local_demo(args: argparse.Namespace) -> int:
    """Run a local request through the current product surface and print JSON."""

    from tailmate.entrypoints.local_env import ensure_local_environment, ensure_local_user_exists

    config = ensure_local_environment()
    trusted_user_id = str(getattr(args, "user_id", "") or "").strip()
    if trusted_user_id:
        ensure_local_user_exists(config, trusted_user_id)
    agent = create_agent_app(environment=AppEnvironment.LOCAL)
    agent.set_up()
    response = agent.query(**build_local_demo_query(args))
    json.dump(response, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0
