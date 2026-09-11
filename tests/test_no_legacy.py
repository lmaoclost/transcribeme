"""Legacy upstream shims are gone: no /download_url, no /process_untranscribed_videos."""

from __future__ import annotations


def test_legacy_routes_absent(client):
    spec = client.get("/openapi.json").json()["paths"]
    assert "/download_url" not in spec
    assert "/process_untranscribed_videos" not in spec
    assert client.post("/download_url", json={"url": "https://example.com"}).status_code == 404
    assert client.post("/process_untranscribed_videos").status_code == 404


def test_legacy_task_unregistered():
    from app.celery_app import celery_app

    assert "app.transcription_processor.process_untranscribed_videos" not in celery_app.tasks
