"""Target-language captions win; NLLB only when target captions are absent."""

from __future__ import annotations

from pathlib import Path

import app.services.youtube_captions as caps


def _vtt(text: str) -> str:
    return f"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n{text}\n"


class _FakeYDL:
    """Drops a .vtt file per requested lang when AVAILABLE has it."""

    AVAILABLE: dict = {}

    def __init__(self, params):
        self.params = params

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        outtmpl = self.params["outtmpl"]
        tmpdir = str(Path(outtmpl).parent)
        for lang in self.params.get("subtitleslangs", []):
            # emulate yt-dlp regex matching: "pt" also matches "pt-BR"
            hit = lang if lang in self.AVAILABLE else next(
                (a for a in self.AVAILABLE if a.startswith(lang + "-")), None
            )
            if hit:
                Path(tmpdir, f"vid123.{hit}.vtt").write_text(_vtt(self.AVAILABLE[hit]))
        return {"id": "vid123"}


def _patch(monkeypatch, available: dict):
    _FakeYDL.AVAILABLE = available
    monkeypatch.setattr(caps, "YoutubeDL", _FakeYDL)


def test_target_captions_win_over_source_captions(monkeypatch):
    # pt-BR video, user wants en: native en captions must win over pt ones
    _patch(monkeypatch, {"pt": "ola mundo", "en": "hello world"})
    result = caps.fetch_youtube_transcript(
        "https://www.youtube.com/watch?v=vid123",
        langs=["pt", "en"],
        target_lang="eng_Latn",
    )
    assert result is not None
    text, lang = result
    assert lang == "en"
    assert "hello world" in text


def test_target_variant_matches_first(monkeypatch):
    # target pt: pt-BR captions win over en
    _patch(monkeypatch, {"pt-BR": "ola mundo", "en": "hello world"})
    result = caps.fetch_youtube_transcript(
        "https://www.youtube.com/watch?v=vid123",
        langs=["en", "pt-BR"],
        target_lang="por_Latn",
    )
    assert result is not None
    text, lang = result
    assert lang == "pt"
    assert "ola mundo" in text


def test_falls_back_to_other_lang_when_no_target_captions(monkeypatch):
    # no en captions anywhere: pt used, caller NLLB-translates
    _patch(monkeypatch, {"pt": "ola mundo"})
    result = caps.fetch_youtube_transcript(
        "https://www.youtube.com/watch?v=vid123",
        langs=["pt", "en"],
        target_lang="eng_Latn",
    )
    assert result is not None
    text, lang = result
    assert lang == "pt"
    assert "ola mundo" in text


def test_nllb_code_maps_to_youtube_lang():
    assert caps.nllb_to_youtube("eng_Latn") == "en"
    assert caps.nllb_to_youtube("por_Latn") == "pt"
    assert caps.nllb_to_youtube("spa_Latn") == "es"
    assert caps.nllb_to_youtube("jpn_Jpan") == "ja"
