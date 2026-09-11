"""Lock in Options modal contract: valid settings persist, invalid ones rejected."""

from __future__ import annotations

import pytest


@pytest.fixture()
def isolated_settings(tmp_path, monkeypatch):
    import app.config

    monkeypatch.setattr(app.config, "SETTINGS_FILE", tmp_path / "settings.json")


def test_update_settings_persists_and_reads_back(client, isolated_settings):
    response = client.post("/settings", json={"whisper_model": "medium", "transcription_speed": 1.0})
    assert response.status_code == 200
    assert response.json()["whisper_model"] == "medium"
    assert response.json()["transcription_speed"] == 1.0

    reread = client.get("/settings")
    assert reread.json()["whisper_model"] == "medium"
    assert reread.json()["transcription_speed"] == 1.0


# schema rejects out-of-range values with 422 before the handler's 400 guard
def test_update_settings_rejects_bad_speed(client, isolated_settings):
    assert client.post("/settings", json={"transcription_speed": 2.0}).status_code == 422


def test_update_settings_rejects_bad_model(client, isolated_settings):
    assert client.post("/settings", json={"whisper_model": "tiny"}).status_code == 422


def test_update_settings_rejects_bad_lang_code(client, isolated_settings):
    assert client.post("/settings", json={"translation_target_lang_code": "xx"}).status_code == 400
