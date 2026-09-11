"""Lock in job lifecycle guards: rerun, cancel, delete granularity."""

from __future__ import annotations

from datetime import datetime, timezone

from app.models import Job, JobEvent, JobStatus


def _make_job(db_session, tmp_path, status=JobStatus.completed, with_media=True, error=None):
    download_path = None
    if with_media:
        media = tmp_path / "video.mp4"
        media.write_bytes(b"fake-media")
        download_path = str(media)
    job = Job(
        source_url="https://example.com/v",
        status=status,
        progress=100.0 if status == JobStatus.completed else 10.0,
        download_path=download_path,
        error=error,
        finished_at=(
            datetime.now(timezone.utc) if status in {JobStatus.completed, JobStatus.failed} else None
        ),
    )
    db_session.add(job)
    db_session.commit()
    return job


class _FakeTranscriptionTask:
    def __init__(self):
        self.calls = []

    def apply_async(self, **kwargs):
        self.calls.append(kwargs)


def test_rerun_completed_job_requeues_and_resets(client, db_session, tmp_path, monkeypatch):
    task = _FakeTranscriptionTask()
    monkeypatch.setattr("app.routers.jobs.transcribe_video", task)

    job = _make_job(db_session, tmp_path, status=JobStatus.completed, error="old boom")

    response = client.post(f"/jobs/{job.id}/rerun")
    assert response.status_code == 202

    db_session.expire_all()
    fresh = db_session.get(Job, job.id)
    assert fresh.status == JobStatus.queued
    assert fresh.error is None
    assert fresh.finished_at is None  # stale timestamp must not survive a rerun
    assert task.calls  # transcription re-enqueued


def test_rerun_active_job_conflicts(client, db_session, tmp_path):
    job = _make_job(db_session, tmp_path, status=JobStatus.transcribing)
    response = client.post(f"/jobs/{job.id}/rerun")
    assert response.status_code == 409


def test_rerun_missing_media_rejected(client, db_session, tmp_path):
    job = _make_job(db_session, tmp_path, status=JobStatus.failed, with_media=False)
    response = client.post(f"/jobs/{job.id}/rerun")
    assert response.status_code == 400


def test_cancel_queued_job_stamps_finished_at(client, db_session, tmp_path):
    job = _make_job(db_session, tmp_path, status=JobStatus.queued, with_media=False)
    assert job.finished_at is None

    response = client.post(f"/jobs/{job.id}/cancel")
    assert response.status_code == 200

    db_session.expire_all()
    fresh = db_session.get(Job, job.id)
    assert fresh.status == JobStatus.canceled
    assert fresh.finished_at is not None  # cancel must close the elapsed-time window
    events = db_session.query(JobEvent).filter_by(job_id=job.id).all()
    assert any(e.event_type == "canceled" for e in events)


def test_cancel_completed_job_conflicts(client, db_session, tmp_path):
    job = _make_job(db_session, tmp_path, status=JobStatus.completed)
    response = client.post(f"/jobs/{job.id}/cancel")
    assert response.status_code == 409


def test_delete_default_keeps_media_file(client, db_session, tmp_path, monkeypatch):
    from pathlib import Path

    # path guard confines deletes to downloads root; bypass it to test purge logic, not the guard
    monkeypatch.setattr("app.routers.jobs._resolve_download_path", lambda p: Path(p))
    job = _make_job(db_session, tmp_path, status=JobStatus.failed)
    job_id, media_path = job.id, job.download_path

    response = client.delete(f"/jobs/{job_id}")
    assert response.status_code == 200
    db_session.expire_all()
    db_session.expunge_all()
    assert db_session.get(Job, job_id) is None
    # default delete removes the row but keeps files on disk
    import os

    assert os.path.exists(media_path)


def test_delete_purge_media_removes_file(client, db_session, tmp_path, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr("app.routers.jobs._resolve_download_path", lambda p: Path(p))
    job = _make_job(db_session, tmp_path, status=JobStatus.failed)
    media_path = job.download_path

    response = client.delete(f"/jobs/{job.id}?purge_media=true")
    assert response.status_code == 200
    import os

    assert not os.path.exists(media_path)
