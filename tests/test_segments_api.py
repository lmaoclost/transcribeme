"""API: GET /jobs/{id}/transcript/{version}/segments reads the sidecar."""
from __future__ import annotations

import json
from pathlib import Path

import app.db as dbmod
import app.routers.jobs as jobs_mod
from app.models import JobStatus, TranscriptVersion
from app.services.jobs import create_job, update_job_status


def _make_completed_job(session, transcript_path: str, segments: list | None):
    job = create_job(session, source_url="https://youtube.com/watch?v=x", title="x")
    session.add(job)
    session.flush()
    Path(transcript_path).write_text("texto", encoding="utf-8")
    if segments is not None:
        sidecar = Path(str(transcript_path) + ".segments.json")
        sidecar.write_text(json.dumps(segments, ensure_ascii=False), encoding="utf-8")
    tv = TranscriptVersion(job_id=job.id, version=1, transcript_path=transcript_path, model_name="caption", source_lang="pt")
    session.add(tv)
    update_job_status(session, job, JobStatus.completed, progress=100.0, transcript_path=transcript_path)
    session.commit()
    return job


def test_segments_endpoint_returns_blocks(test_app, client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "SessionLocal", db_session)
    monkeypatch.setattr(jobs_mod, "_resolve_download_path", lambda p: Path(p))
    test_app.dependency_overrides[jobs_mod.get_session] = lambda: db_session
    cap = tmp_path / "video-x.captions.txt"
    blocks = [{"start": "00:01", "end": "00:29", "text": "bem-vindos"}]
    job = _make_completed_job(db_session, str(cap), blocks)
    r = client.get(f"/jobs/{job.id}/transcript/1/segments")
    assert r.status_code == 200
    assert r.json() == blocks


def test_segments_endpoint_404_for_legacy(test_app, client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "SessionLocal", db_session)
    monkeypatch.setattr(jobs_mod, "_resolve_download_path", lambda p: Path(p))
    test_app.dependency_overrides[jobs_mod.get_session] = lambda: db_session
    cap = tmp_path / "legacy.txt"
    job = _make_completed_job(db_session, str(cap), None)
    r = client.get(f"/jobs/{job.id}/transcript/1/segments")
    assert r.status_code == 404
    assert "segments not available" in r.json()["detail"]


def test_segments_sidecar_naming():
    from app.routers.jobs import _segments_sidecar_path

    assert _segments_sidecar_path("/d/video.mp4.txt.v2").name == "video.mp4.txt.v2.segments.json"
    assert _segments_sidecar_path("/d/video.captions.txt").name == "video.captions.txt.segments.json"
