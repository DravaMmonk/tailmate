"""Media upload adapter backed by the Cloud Run gateway."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

from tailmate.adapters.db_gateway.client import DbGatewayClient
from tailmate.agent_runtime.current_context import get_current_context
from tailmate.contracts.errors import DomainError
from tailmate.contracts.types import (
    StripMetadataRequest,
    StripMetadataResult,
    normalize_strip_metadata_result,
)


@dataclass
class GatewaySanitizedMediaStore:
    """Delegate metadata stripping and storage to the Cloud Run gateway."""

    client: DbGatewayClient

    def strip_and_store(self, request: StripMetadataRequest) -> StripMetadataResult:
        try:
            payload = base64.b64decode(request["payload_base64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise DomainError("strip_metadata payload_base64 must be valid base64 data.") from exc

        current_context = get_current_context()
        session_id = request.get("session_id")
        if not session_id and current_context is not None:
            session_id = current_context.session_id

        response = self.client.upload_media(
            dog_id=request["dog_id"],
            resource_kind=request["resource_kind"],
            filename=request["filename"],
            content_type=request["content_type"],
            payload=payload,
            session_id=session_id,
        )
        return normalize_strip_metadata_result(response)
