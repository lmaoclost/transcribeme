"""Upload endpoints: direct POST /jobs/upload + chunked /uploads/* flow."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import JobStatus
from app.routers.deps import settings
from app.schemas import JobResponse
from app.services import uploads as upload_svc
from app.services.jobs import add_job_event, create_batch, create_job, update_batch_status
from app.transcription_processor import transcribe_video

router = APIRouter()


@router.post("/jobs/upload", response_model=JobResponse, status_code=202)
async def upload_job(file: UploadFile = File(...), session: Session = Depends(get_session)) -> JobResponse:
    if not file.filename or not upload_svc.is_allowed_file(file.filename):
        raise HTTPException(status_code=400, detail="Only mp4 and mp3 allowed")
    # check size limit
    content = await file.read()
    if len(content) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    # save directly
    upload_id = str(uuid4())
    final = upload_svc.get_final_path(file.filename, upload_id)
    final.parent.mkdir(parents=True, exist_ok=True)
    final.write_bytes(content)
    # create batch + job with input_type upload, no download queue, directly queue transcription
    batch = create_batch(session, source_url=f"upload:{file.filename}")
    job = create_job(session, source_url=f"upload:{file.filename}", batch_id=batch.id, title=Path(file.filename).stem, uploader="upload", input_type="upload", original_filename=file.filename)
    job.download_path = str(final)
    job.status = JobStatus.downloaded
    job.progress = 50.0
    session.add(job)
    add_job_event(session, job.id, "downloaded", f"Upload received {file.filename}", 50.0)
    session.commit()
    update_batch_status(session, batch.id)
    session.commit()
    transcribe_video.apply_async(args=[job.id], queue="transcription_queue")
    return job


# Chunked resumable uploads
@router.post("/uploads/init")
def init_upload(filename: str = Query(...), total_size: int = Query(..., ge=1)) -> dict:
    if not upload_svc.is_allowed_file(filename):
        raise HTTPException(status_code=400, detail="Only mp4 and mp3 allowed")
    if total_size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large")
    upload_id = str(uuid4())
    # create empty part
    part = upload_svc.get_upload_path(upload_id)
    part.parent.mkdir(parents=True, exist_ok=True)
    part.touch()
    return {"upload_id": upload_id, "chunk_size_mb": settings.upload_chunk_size_mb}


@router.patch("/uploads/{upload_id}")
async def upload_chunk(upload_id: str, request: Request) -> dict:
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty chunk")
    part = upload_svc.append_chunk(upload_id, data)
    size = part.stat().st_size
    return {"upload_id": upload_id, "received": size}


@router.get("/uploads/{upload_id}/status")
def upload_status(upload_id: str) -> dict:
    size = upload_svc.get_uploaded_size(upload_id)
    return {"upload_id": upload_id, "received": size}


@router.post("/uploads/{upload_id}/complete", response_model=JobResponse, status_code=202)
def complete_upload(upload_id: str, filename: str = Query(...), session: Session = Depends(get_session)) -> JobResponse:
    if not upload_svc.is_allowed_file(filename):
        raise HTTPException(status_code=400, detail="Only mp4 and mp3 allowed")
    try:
        final = upload_svc.finalize_upload(upload_id, filename)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Upload not found")
    batch = create_batch(session, source_url=f"upload:{filename}")
    job = create_job(session, source_url=f"upload:{filename}", batch_id=batch.id, title=Path(filename).stem, uploader="upload", input_type="upload", original_filename=filename)
    job.download_path = str(final)
    job.status = JobStatus.downloaded
    job.progress = 50.0
    session.add(job)
    add_job_event(session, job.id, "downloaded", f"Chunked upload completed {filename}", 50.0)
    session.commit()
    update_batch_status(session, batch.id)
    session.commit()
    transcribe_video.apply_async(args=[job.id], queue="transcription_queue")
    return job
