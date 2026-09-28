"""Unit: translate_segments preserves timestamps, uses per-block translate."""
from __future__ import annotations

import app.services.translation as tr


def test_translate_segments_per_block(monkeypatch):
    calls = []

    def fake_translate(text, src_lang, tgt_code=None):
        calls.append(text)
        return f"[{text.upper()}]"

    monkeypatch.setattr(tr, "needs_translation", lambda lang: True)
    monkeypatch.setattr(tr, "translate", fake_translate)

    blocks = [
        {"start": "00:01", "end": "00:29", "text": "hello"},
        {"start": "00:29", "end": "00:44", "text": ""},
    ]
    out = tr.translate_segments(blocks, "en", "por_Latn")
    assert calls == ["hello"]
    assert out[0] == {"start": "00:01", "end": "00:29", "text": "[HELLO]"}
    assert out[1]["start"] == "00:29" and out[1]["text"] == ""


def test_translate_segments_noop_when_same_language(monkeypatch):
    monkeypatch.setattr(tr, "needs_translation", lambda lang: False)
    blocks = [{"start": "00:00", "end": "00:10", "text": "já é pt"}]
    out = tr.translate_segments(blocks, "pt", "por_Latn")
    assert out == blocks
