"""Cleanup old jobs after 7 days."""

from datetime import datetime, timedelta
from pathlib import Path

from celery.utils.log import get_task_logger
from sqlalchemy import select, delete

from app.celery_app import celery_app
from app.config import get_settings
from app import db
from app.models import Job, JobEvent, TranscriptVersion

logger = get_task_logger(__name__)
settings = get_settings()

@celery_app.task(name="app.tasks.cleanup.cleanup_old_jobs")
def cleanup_old_jobs() -> dict:
    cutoff = datetime.utcnow() - timedelta(days=settings.cleanup_days)
    count = 0
    with db.SessionLocal() as session:
        old_jobs = session.scalars(select(Job).where(Job.finished_at != None, Job.finished_at < cutoff)).all()
        for job in old_jobs:
            # delete files
            for path_value in [job.download_path, job.transcript_path]:
                if not path_value:
                    continue
                try:
                    p = Path(path_value)
                    if p.exists():
                        # ensure inside downloads
                        downloads_root = Path(settings.downloads_dir).resolve()
                        if downloads_root in p.resolve().parents or p.resolve() == downloads_root:
                            p.unlink()
                except Exception as exc:
                    logger.warning("cleanup unlink failed %s: %s", path_value, exc)
            versions = session.scalars(select(TranscriptVersion).where(TranscriptVersion.job_id == job.id)).all()
            for v in versions:
                try:
                    p = Path(v.transcript_path)
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass
            session.execute(delete(TranscriptVersion).where(TranscriptVersion.job_id == job.id))
            session.execute(delete(JobEvent).where(JobEvent.job_id == job.id))
            session.delete(job)
            count += 1
        session.commit()
        logger.info("Cleanup removed %s jobs older than %s days", count, settings.cleanup_days)
        return {"removed": count}

# Schedule via beat
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "cleanup-old-jobs-daily": {
        "task": "app.tasks.cleanup.cleanup_old_jobs",
        "schedule": crontab(hour=3, minute=0),  # daily 03:00
    }
}
celery_app.conf.timezone = "UTC"
