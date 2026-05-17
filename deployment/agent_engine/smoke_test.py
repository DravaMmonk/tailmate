"""Remote smoke test for a deployed Vertex AI Agent Engine custom agent."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
import sys

import vertexai
from dotenv import load_dotenv


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def require_any_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    joined = ", ".join(names)
    raise RuntimeError(f"Missing required environment variable. Expected one of: {joined}")


def build_strip_metadata_request() -> dict[str, str] | None:
    media_path_value = os.getenv("TAILMATE_SMOKE_MEDIA_PATH")
    if not media_path_value:
        return None

    media_path = Path(media_path_value).expanduser().resolve()
    if not media_path.is_file():
        raise RuntimeError(f"TAILMATE_SMOKE_MEDIA_PATH does not point to a file: {media_path}")

    content_type = (
        os.getenv("TAILMATE_SMOKE_MEDIA_CONTENT_TYPE")
        or mimetypes.guess_type(media_path.name)[0]
        or "application/octet-stream"
    )
    resource_kind = os.getenv("TAILMATE_SMOKE_RESOURCE_KIND")
    if not resource_kind:
        resource_kind = "videos" if content_type.startswith("video/") else "images"

    return {
        "dog_id": os.getenv("TAILMATE_SMOKE_DOG_ID", "smoke-dog"),
        "resource_kind": resource_kind,
        "filename": media_path.name,
        "content_type": content_type,
        "payload_base64": base64.b64encode(media_path.read_bytes()).decode("utf-8"),
    }


def main() -> None:
    load_dotenv()
    project = require_any_env("GOOGLE_CLOUD_PROJECT", "TAILMATE_PROJECT_ID")
    location = require_any_env("GOOGLE_CLOUD_LOCATION", "CLOUD_ML_REGION", "TAILMATE_LOCATION")
    resource_name = require_env("TAILMATE_AGENT_ENGINE_RESOURCE_NAME")
    session_id = os.getenv("TAILMATE_SMOKE_SESSION_ID", "smoke-session")
    message = os.getenv("TAILMATE_SMOKE_MESSAGE", "health check")
    dog_id = os.getenv("TAILMATE_SMOKE_DOG_ID", "smoke-dog")
    metadata = {"dog_id": dog_id}
    smoke_user_id = (os.getenv("TAILMATE_SMOKE_USER_ID") or "").strip()
    if smoke_user_id:
        metadata["user_id"] = smoke_user_id
    strip_metadata_request = build_strip_metadata_request()
    if strip_metadata_request is not None:
        metadata["strip_metadata_request"] = strip_metadata_request

    client = vertexai.Client(project=project, location=location)
    remote_agent = client.agent_engines.get(name=resource_name)
    response = remote_agent.query(
        input={
            "session_id": session_id,
            "message": message,
            "metadata": metadata,
        }
    )
    json.dump(response, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
