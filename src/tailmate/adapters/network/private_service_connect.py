"""Private Service Connect network attachment boundary helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkAttachmentConfig:
    """Captures the network attachment used for private backend reachability."""

    attachment_name: str
