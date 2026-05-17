"""Audio transcription adapters for sanitized media flows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from google.auth.credentials import Credentials
import tenacity
import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel, Part

from tailmate.agent_runtime.ports.audio_transcriber import AudioTranscriber, AudioTranscription
from tailmate.contracts.errors import AdapterError


RETRY_ATTEMPTS = 3
RETRY_INITIAL_WAIT_SECONDS = 1
RETRY_MAX_WAIT_SECONDS = 4
TRANSCRIPTION_PROMPT = (
    "Transcribe this dog-care voice message into plain text. "
    "Return only the spoken words without markdown, speaker labels, or commentary. "
    "If the audio is empty or unintelligible, return an empty string."
)


def _retry_external_call(
    *,
    operation: Callable[[], Any],
    failure_message: str,
) -> Any:
    retrying = tenacity.Retrying(
        sleep=tenacity.sleep,
        stop=tenacity.stop_after_attempt(RETRY_ATTEMPTS),
        wait=tenacity.wait_exponential(
            multiplier=RETRY_INITIAL_WAIT_SECONDS,
            min=RETRY_INITIAL_WAIT_SECONDS,
            max=RETRY_MAX_WAIT_SECONDS,
        ),
        retry=tenacity.retry_if_exception_type(Exception),
        reraise=False,
    )
    try:
        return retrying(operation)
    except tenacity.RetryError as exc:
        last_attempt = exc.last_attempt
        last_exception = last_attempt.exception() if last_attempt is not None else None
        if last_exception is not None:
            raise AdapterError(failure_message) from last_exception
        raise AdapterError(failure_message) from exc


@dataclass
class GeminiAudioTranscriber(AudioTranscriber):
    """Transcribe audio bytes with Gemini multimodal input."""

    model_name: str
    project_id: str
    location: str
    api_key: str | None = None
    credentials: Credentials | None = None
    timeout_seconds: int = 30
    initializer: Callable[..., None] = vertexai.init
    model_factory: Callable[[str], Any] = GenerativeModel
    _model: Any | None = field(default=None, init=False, repr=False)
    _init_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def transcribe(self, payload: bytes, *, content_type: str) -> AudioTranscription:
        response = _retry_external_call(
            operation=lambda: self._ensure_model().generate_content(
                [
                    TRANSCRIPTION_PROMPT,
                    Part.from_data(payload, mime_type=content_type),
                ],
                generation_config=GenerationConfig(
                    temperature=0.0,
                ),
                request_options={"timeout": self.timeout_seconds},
            ),
            failure_message=(
                f"Failed to reach Gemini model '{self.model_name}' for audio transcription."
            ),
        )
        text = str(getattr(response, "text", "") or "").strip()
        if not text:
            raise AdapterError("Gemini returned an empty audio transcription payload.")
        return AudioTranscription(text=text, model_name=self.model_name)

    def _ensure_model(self) -> Any:
        if self._model is not None:
            return self._model
        with self._init_lock:
            if self._model is None:
                self.initializer(
                    project=self.project_id,
                    location=self.location,
                    credentials=self.credentials,
                    api_key=self.api_key,
                )
                self._model = self.model_factory(self.model_name)
        return self._model
