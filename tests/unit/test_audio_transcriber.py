from __future__ import annotations

import pytest

from tailmate.adapters.media.audio_transcriber import GeminiAudioTranscriber, TRANSCRIPTION_PROMPT
from tailmate.contracts.errors import AdapterError


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModel:
    def __init__(self, response_text: str, *, fail_times: int = 0) -> None:
        self.response_text = response_text
        self.fail_times = fail_times
        self.calls: list[dict[str, object]] = []

    def generate_content(self, contents, **kwargs):
        self.calls.append({"contents": contents, "kwargs": kwargs})
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("temporary failure")
        return FakeResponse(self.response_text)


def test_gemini_audio_transcriber_sends_audio_part_and_returns_text() -> None:
    model = FakeModel("Buddy ate breakfast.")
    init_calls: list[dict[str, object]] = []
    transcriber = GeminiAudioTranscriber(
        model_name="gemini-2.5-flash",
        project_id="project-1",
        location="global",
        initializer=lambda **kwargs: init_calls.append(kwargs),
        model_factory=lambda _model_name: model,
    )

    result = transcriber.transcribe(b"audio-bytes", content_type="audio/mpeg")

    assert result.text == "Buddy ate breakfast."
    assert result.model_name == "gemini-2.5-flash"
    assert init_calls == [
        {
            "project": "project-1",
            "location": "global",
            "credentials": None,
            "api_key": None,
        }
    ]
    contents = model.calls[0]["contents"]
    assert contents[0] == TRANSCRIPTION_PROMPT
    assert contents[1].mime_type == "audio/mpeg"
    assert contents[1].inline_data.data == b"audio-bytes"


def test_gemini_audio_transcriber_retries_transient_failures() -> None:
    model = FakeModel("Buddy is limping.", fail_times=2)
    transcriber = GeminiAudioTranscriber(
        model_name="gemini-2.5-flash",
        project_id="project-1",
        location="global",
        initializer=lambda **_: None,
        model_factory=lambda _model_name: model,
    )

    result = transcriber.transcribe(b"audio-bytes", content_type="audio/ogg")

    assert result.text == "Buddy is limping."
    assert len(model.calls) == 3


def test_gemini_audio_transcriber_rejects_empty_text() -> None:
    transcriber = GeminiAudioTranscriber(
        model_name="gemini-2.5-flash",
        project_id="project-1",
        location="global",
        initializer=lambda **_: None,
        model_factory=lambda _model_name: FakeModel("   "),
    )

    with pytest.raises(AdapterError, match="empty audio transcription payload"):
        transcriber.transcribe(b"audio-bytes", content_type="audio/mp4")
