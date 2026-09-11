"""Job endpoints: queue, list, detail, rerun, cancel, delete, events, transcripts, media."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.download_processor import enqueue_url
from app.models import Job, JobEvent, JobStatus, TranscriptVersion
from app.routers.deps import _resolve_download_path
from app.schemas import (
    BatchCreateResponse,
    DeleteJobResponse,
    JobCreateRequest,
    JobEventResponse,
    JobListResponse,
    JobResponse,
    TranscriptVersionResponse,
)
from app.services.jobs import add_job_event, create_batch, create_job, update_batch_status
from app.transcription_processor import transcribe_video

router = APIRouter()


@router.post("/jobs", response_model=BatchCreateResponse, status_code=202)
def create_jobs(request: JobCreateRequest, session: Session = Depends(get_session)) -> BatchCreateResponse:
    batch = create_batch(session, request.url)
    # optimistic Job so queue shows instantly, even while another job is processing
    job = create_job(session, source_url=request.url, batch_id=batch.id, video_url=request.url, title=request.url, uploader="YouTube", input_type="url", requested_format=request.format_id)
    add_job_event(session, job.id, "queued", "Queued for processing", 0.0)
    session.commit()
    enqueue_url.delay(batch.id, request.url, request.format_id, job.id)
    return BatchCreateResponse(batch_id=batch.id, message="Queued for processing")


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    status: Optional[JobStatus] = Query(default=None),
    batch_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> JobListResponse:
    stmt = select(Job)
    count_stmt = select(func.count()).select_from(Job)
    if status:
        stmt = stmt.where(Job.status == status)
        count_stmt = count_stmt.where(Job.status == status)
    if batch_id:
        stmt = stmt.where(Job.batch_id == batch_id)
        count_stmt = count_stmt.where(Job.batch_id == batch_id)
    total = session.scalar(count_stmt) or 0
    jobs = session.scalars(stmt.order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
    return JobListResponse(jobs=jobs, total=total)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs/{job_id}/rerun", status_code=202)
def rerun_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {JobStatus.downloading, JobStatus.transcribing}:
        raise HTTPException(status_code=409, detail="Cannot rerun active job")
    if not job.download_path or not Path(job.download_path).exists():
        raise HTTPException(status_code=400, detail="Media file missing, cannot rerun")
    job.status = JobStatus.queued
    job.progress = 50.0
    job.error = None
    job.finished_at = None
    session.add(job)
    add_job_event(session, job.id, "queued", "Rerun queued for transcription", 50.0)
    session.commit()
    transcribe_video.apply_async(args=[job.id], queue="transcription_queue")
    return {"message": "Rerun queued", "job_id": job.id}


@router.post("/jobs/{job_id}/cancel", status_code=200)
def cancel_job(job_id: str, session: Session = Depends(get_session)) -> dict:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in {JobStatus.queued, JobStatus.downloading}:
        raise HTTPException(status_code=409, detail="Only queued/downloading jobs can be canceled")
    job.status = JobStatus.canceled
    job.finished_at = datetime.now(timezone.utc)
    session.add(job)
    add_job_event(session, job.id, "canceled", "Job canceled by user")
    # try revoke celery if downloading
    try:
        from app.celery_app import celery_app
        celery_app.control.revoke(job.id, terminate=False)
    except Exception:
        pass
    session.commit()
    if job.batch_id:
        update_batch_status(session, job.batch_id)
        session.commit()
    return {"message": "Canceled", "job_id": job.id}


@router.delete("/jobs/{job_id}", response_model=DeleteJobResponse)
def delete_job(
    job_id: str,
    purge_media: bool = Query(default=False),
    purge_transcript: bool = Query(default=False),
    purge_files: Optional[bool] = Query(default=None),
    session: Session = Depends(get_session),
) -> DeleteJobResponse:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {JobStatus.downloading, JobStatus.transcribing}:
        raise HTTPException(status_code=409, detail="Cannot delete an active job")
    # backward compat: purge_files means both
    if purge_files is not None:
        purge_media = purge_media or purge_files
        purge_transcript = purge_transcript or purge_files
    # if neither specified, delete job only (keep files); checkboxes choose
    if purge_media and job.download_path:
        candidate = _resolve_download_path(job.download_path)
        if candidate.exists():
            # ensure inside downloads
            candidate.unlink()
    if purge_transcript:
        # delete all transcript versions + main
        versions = session.scalars(select(TranscriptVersion).where(TranscriptVersion.job_id == job.id)).all()
        for v in versions:
            try:
                p = _resolve_download_path(v.transcript_path)
                if p.exists():
                    p.unlink()
            except HTTPException:
                pass
        if job.transcript_path:
            try:
                candidate = _resolve_download_path(job.transcript_path)
                if candidate.exists():
                    candidate.unlink()
            except HTTPException:
                pass
        session.execute(delete(TranscriptVersion).where(TranscriptVersion.job_id == job_id))
    batch_id = job.batch_id
    session.execute(delete(JobEvent).where(JobEvent.job_id == job_id))
    if not purge_transcript:
        # if we keep transcripts but delete job, need to delete versions anyway? keep files but remove DB
        session.execute(delete(TranscriptVersion).where(TranscriptVersion.job_id == job_id))
    session.delete(job)
    session.flush()
    if batch_id:
        update_batch_status(session, batch_id)
    session.commit()
    return DeleteJobResponse(job_id=job_id, message="Job removed")


@router.get("/jobs/{job_id}/events", response_model=List[JobEventResponse])
def get_job_events(job_id: str, session: Session = Depends(get_session)) -> List[JobEventResponse]:
    events = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at.asc())).all()
    return events


@router.get("/jobs/{job_id}/transcripts", response_model=List[TranscriptVersionResponse])
def list_transcripts(job_id: str, session: Session = Depends(get_session)) -> List[TranscriptVersionResponse]:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    versions = session.scalars(select(TranscriptVersion).where(TranscriptVersion.job_id == job_id).order_by(TranscriptVersion.version.asc())).all()
    return versions


@router.get("/jobs/{job_id}/transcript/{version}")
def get_transcript_version(job_id: str, version: int, session: Session = Depends(get_session)) -> PlainTextResponse:
    tv = session.scalar(select(TranscriptVersion).where(TranscriptVersion.job_id == job_id, TranscriptVersion.version == version))
    if not tv:
        raise HTTPException(status_code=404, detail="Version not found")
    path = _resolve_download_path(tv.transcript_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Transcript file not found")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="ignore"))


@router.delete("/jobs/{job_id}/transcript/{version}")
def delete_transcript_version(job_id: str, version: int, session: Session = Depends(get_session)) -> dict:
    tv = session.scalar(select(TranscriptVersion).where(TranscriptVersion.job_id == job_id, TranscriptVersion.version == version))
    if not tv:
        raise HTTPException(status_code=404, detail="Version not found")
    try:
        p = _resolve_download_path(tv.transcript_path)
        if p.exists():
            p.unlink()
    except HTTPException:
        pass
    # if deleting latest version, update job.transcript_path to previous
    job = session.get(Job, job_id)
    session.delete(tv)
    session.flush()
    if job:
        remaining = session.scalars(select(TranscriptVersion).where(TranscriptVersion.job_id == job_id).order_by(TranscriptVersion.version.desc())).first()
        job.transcript_path = remaining.transcript_path if remaining else None
        session.add(job)
    session.commit()
    return {"message": "Version deleted", "job_id": job_id, "version": version}


@router.get("/jobs/{job_id}/media")
def get_job_media(job_id: str, session: Session = Depends(get_session)) -> FileResponse:
    job = session.get(Job, job_id)
    if not job or not job.download_path:
        raise HTTPException(status_code=404, detail="Media file not found")
    media_path = _resolve_download_path(job.download_path)
    if not media_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    media_type, _ = mimetypes.guess_type(media_path.name)
    return FileResponse(media_path, media_type=media_type or "application/octet-stream", filename=media_path.name)


@router.get("/jobs/{job_id}/transcript")
def get_job_transcript(job_id: str, session: Session = Depends(get_session)) -> PlainTextResponse:
    job = session.get(Job, job_id)
    if not job or not job.transcript_path:
        raise HTTPException(status_code=404, detail="Transcript not found")
    transcript_path = _resolve_download_path(job.transcript_path)
    if not transcript_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    transcript_text = transcript_path.read_text(encoding="utf-8", errors="ignore")
    return PlainTextResponse(transcript_text)
