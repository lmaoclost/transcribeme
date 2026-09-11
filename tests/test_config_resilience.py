"""Lock in ZimaOS/CasaOS env resilience: blank, unexpanded ${...}, and garbage values fall back to defaults."""

from __future__ import annotations

from app.config import Settings


def test_unexpanded_interpolation_falls_back_to_defaults(monkeypatch):
    # CasaOS passes the literal string when it skips ${VAR:-default} expansion
    monkeypatch.setenv("QTUBE_CLEANUP_DAYS", "${QTUBE_CLEANUP_DAYS:-7}")
    monkeypatch.setenv("QTUBE_TRANSCRIPTION_SPEED", "${QTUBE_TRANSCRIPTION_SPEED:-1.5}")
    monkeypatch.setenv("QTUBE_WHISPER_MODEL", "${QTUBE_WHISPER_MODEL:-small}")
    monkeypatch.setenv("QTUBE_TRANSLATION_MODEL", "${QTUBE_TRANSLATION_MODEL:-facebook/nllb-200-distilled-600M}")

    s = Settings()
    assert s.cleanup_days == 7
    assert s.transcription_speed == 1.5
    assert s.whisper_model == "small"
    assert s.translation_model == "facebook/nllb-200-distilled-600M"


def test_blank_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("QTUBE_CLEANUP_DAYS", "")
    monkeypatch.setenv("QTUBE_TRANSCRIPTION_SPEED", "")
    monkeypatch.setenv("QTUBE_WHISPER_MODEL", "")

    s = Settings()
    assert s.cleanup_days == 7
    assert s.transcription_speed == 1.5
    assert s.whisper_model == "small"


def test_garbage_numerics_fall_back_to_defaults():
    s = Settings(cleanup_days="garbage", transcription_speed="not-a-float")
    assert s.cleanup_days == 7
    assert s.transcription_speed == 1.5


def test_string_bool_parses():
    assert Settings(youtube_prefer_captions="false").youtube_prefer_captions is False
    assert Settings(youtube_prefer_captions="0").youtube_prefer_captions is False
    assert Settings(youtube_prefer_captions="true").youtube_prefer_captions is True
    assert Settings(youtube_prefer_captions="${QTUBE_YOUTUBE_PREFER_CAPTIONS:-True}").youtube_prefer_captions is True


def test_valid_values_pass_through():
    s = Settings(cleanup_days=14, transcription_speed=1.0, whisper_model="medium")
    assert s.cleanup_days == 14
    assert s.transcription_speed == 1.0
    assert s.whisper_model == "medium"
