"""Unit: VTT cue parsing + ~30s block grouping (timestamps preserved)."""
from __future__ import annotations

from app.services.youtube_captions import clean_vtt_segments, parse_vtt_cues

VTT = """WEBVTT
Kind: captions
Language: pt

1
00:00:01.000 --> 00:00:14.000
Olá pessoal, bem-vindos

2
00:00:14.000 --> 00:00:29.000
hoje vamos falar de IA

3
00:00:29.000 --> 00:00:44.000
[Music]
e programação

4
00:00:44.000 --> 00:01:20.000
o jeito errado de usar IA para estudar
programação é pular fundamentos

5
00:01:20.000 --> 00:01:52.000
copilot não substitui saber
"""


def test_parse_vtt_cues_extracts_timing_and_text():
    cues = parse_vtt_cues(VTT)
    assert cues[0] == (1.0, 14.0, "Olá pessoal, bem-vindos")
    assert len(cues) == 5
    assert "[Music]" not in " ".join(c[2] for c in cues)


def test_blocks_are_about_30s_and_never_over_35s():
    blocks = clean_vtt_segments(VTT)
    assert all("start" in b and "end" in b and "text" in b for b in blocks)

    def _sec(ts):
        m, s = ts.split(":")
        return int(m) * 60 + int(s)

    for b in blocks:
        dur = _sec(b["end"]) - _sec(b["start"])
        assert dur <= 35, f"block too long: {b['start']}->{b['end']} ({dur}s)"
    # block0 accumulates cues 1+2 (28s); cue3 would push past max 35s -> new block
    assert blocks[0]["start"] == "00:01"
    assert blocks[0]["text"] == "Olá pessoal, bem-vindos hoje vamos falar de IA"
    assert blocks[0]["end"] == "00:29"


def test_single_short_video_returns_one_block():
    vtt = """WEBVTT

00:00:00.000 --> 00:00:12.000
texto curto
"""
    blocks = clean_vtt_segments(vtt)
    assert blocks == [{"start": "00:00", "end": "00:12", "text": "texto curto"}]