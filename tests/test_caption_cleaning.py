"""Lock in YouTube caption cleaning: plain text out, no timestamps/markup/noise."""

from __future__ import annotations

from app.services.youtube_captions import clean_vtt_text


def test_strips_webvtt_headers_timestamps_and_numbers():
    raw = "WEBVTT\nKind: captions\nLanguage: en\n\n1\n00:00:00.000 --> 00:00:02.000\nhello world\n"
    assert clean_vtt_text(raw) == "hello world"


def test_strips_inline_tags_speakers_and_music():
    raw = (
        "00:00:01.000 --> 00:00:03.000\n"
        "<00:00:01.000><c>hello</c> <c>there</c>\n"
        "00:00:03.000 --> 00:00:05.000\n"
        ">> Alice: how are you\n"
        "00:00:05.000 --> 00:00:07.000\n"
        "[Music]\n"
        "00:00:07.000 --> 00:00:09.000\n"
        "[música] fim\n"
    )
    text = clean_vtt_text(raw)
    assert "WEBVTT" not in text
    assert "-->" not in text
    assert "<c>" not in text and "<00:" not in text
    assert ">>" not in text and "Alice:" not in text
    assert "[Music]" not in text and "[música]" not in text
    assert "hello there" in text
    assert "how are you" in text


def test_dedups_consecutive_repeats():
    raw = (
        "00:00:01.000 --> 00:00:02.000\nhello\n"
        "00:00:02.000 --> 00:00:03.000\nhello\n"
        "00:00:03.000 --> 00:00:04.000\nworld\n"
    )
    assert clean_vtt_text(raw) == "hello world"
