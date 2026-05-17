"""Media-processing adapters."""

from __future__ import annotations


__all__ = ["DirectSanitizedMediaStore"]


def __getattr__(name: str):
    if name == "DirectSanitizedMediaStore":
        from tailmate.adapters.media.sanitized_media_store import DirectSanitizedMediaStore

        return DirectSanitizedMediaStore
    raise AttributeError(name)
