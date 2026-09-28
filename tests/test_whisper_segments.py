"""Unit: whisper segments -> ~30s blocks (mocked model)."""
from __future__ import annotations

from types import SimpleNamespace

import app.whisper_transcriber as wt


class FakeModel:
    def transcribe(self, path, language=None):
        segs = [
            SimpleNamespace(start=0.0, end=15.0, text="primeira frase "),
            SimpleNamespace(start=15.0, end=29.0, text="segunda frase"),
            SimpleNamespace(start=29.0, end=44.0, text="terceira frase"),
        ]
        info = SimpleNamespace(language="pt", language_probability=0.9)
        return iter(segs), info


def test_transcribe_audio_segments_blocks(monkeypatch):
    from pathlib import Path

    t = object.__new__(wt.WhisperTranscriber)
    t.model = FakeModel()
    blocks, lang = t.transcribe_audio_segments(Path("/tmp/x.webm"))
    assert lang == "pt"
    assert blocks[0]["text"] == "primeira frase segunda frase"
    assert blocks[0]["end"] == "00:29"
    assert all(b["text"] for b in blocks)


def test_transcribe_audio_text_joins_blocks():
    from pathlib import Path

    t = object.__new__(wt.WhisperTranscriber)
    t.model = FakeModel()
    text, lang = t.transcribe_audio(Path("/tmp/x.webm"))
    assert lang == "pt"
    assert text == "primeira frase segunda frase terceira frase"
