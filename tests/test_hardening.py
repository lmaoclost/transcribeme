"""Hardening: missing-file fail-fast + ffmpeg timeout scaling + explicit failures."""
from __future__ import annotations

import re

from app.audio_tools import _ffmpeg_timeout


def test_missing_input_raises_instead_of_silent_pass():
    import tempfile
    from pathlib import Path

    from app.audio_tools import accelerate_audio

    missing = Path(tempfile.mkdtemp()) / "nope.webm"
    try:
        accelerate_audio(missing, 1.5)
        raise AssertionError("should have raised FileNotFoundError")
    except FileNotFoundError as e:
        assert "nope.webm" in str(e)


def test_ffmpeg_timeout_scales_with_size(tmp_path):
    small = tmp_path / "small.webm"
    small.write_bytes(b"x" * (50 * 1024 * 1024))  # 50MB -> 60+30=90s
    big = tmp_path / "big.webm"
    big.write_bytes(b"x" * (800 * 1024 * 1024))  # 800MB -> 60+8*60=540s
    huge = tmp_path / "huge.webm"
    huge.write_bytes(b"x" * (4096 * 1024 * 1024))  # 4GB -> cap 1200s

    assert _ffmpeg_timeout(small) == 90
    assert _ffmpeg_timeout(big) == 60 + 8 * 60
    assert _ffmpeg_timeout(huge) == 1200


def test_ffmpeg_failure_raises_not_returns_original(tmp_path, monkeypatch):
    import subprocess

    from app.audio_tools import accelerate_audio

    src = tmp_path / "in.webm"
    src.write_bytes(b"data")

    def boom(*args, **kwargs):
        result = subprocess.CompletedProcess(args, returncode=1, stdout="", stderr="err")
        raise RuntimeError

    # simulate: subprocess.run returns rc=1 (no exception path)
    class FakeCompleted:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr("subprocess.run", lambda *a, **k: FakeCompleted())
    try:
        accelerate_audio(src, 1.5)
        raise AssertionError("should have raised RuntimeError")
    except RuntimeError as e:
        assert "ffmpeg accelerate failed" in str(e)


def test_fragment_regex_matches_multistream_fragments():
    RE = re.compile(r"\.f\d+(?:-\d+)?(?:-part)?\.(?:mp4|webm|mkv|m4a|part)$")
    assert RE.search("video.f251-2.webm")
    assert RE.search("video.f137.mp4")
    assert not RE.search("final.mkv")
