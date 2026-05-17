"""Port for model-generated conversational fallback answers."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterator
from typing import Protocol

from tailmate.contracts.types import ResponseProvenance


@dataclass(frozen=True)
class ConversationalRequest:
    """Normalized request for an open-domain conversational answer."""

    user_message: str
    locale: str
    dog_context: str | None
    recent_turns: tuple[dict, ...]
    system_scope: str


@dataclass(frozen=True)
class ConversationalResponse:
    """Structured model-generated conversational answer."""

    text: str
    provenance: ResponseProvenance
    model: str
    usage: dict[str, int]


class ConversationalResponder(Protocol):
    """Generate a scoped conversational fallback response."""

    def generate(self, request: ConversationalRequest) -> ConversationalResponse: ...

    def stream_generate(self, request: ConversationalRequest) -> Iterator[str]: ...
