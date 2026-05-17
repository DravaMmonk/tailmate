"""Audio transcription contracts used by media ingestion flows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AudioTranscription:
    """Structured transcription payload returned by audio adapters."""

    text: str
    model_name: str


class AudioTranscriber(Protocol):
    """Convert sanitized audio bytes into assistant-readable text."""

    def transcribe(self, payload: bytes, *, content_type: str) -> AudioTranscription: ...
