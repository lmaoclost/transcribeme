"""FastAPI server for transcribeme - YouTube + direct URL + upload queue with translate to pt-BR."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
import mimetypes

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from yt_dlp import YoutubeDL

from app.config import get_settings, save_settings
from app.db import get_session, init_db
from app.download_processor import _base_ydl_params, enqueue_url
from app.transcription_processor import process_untranscribed_videos, transcribe_video
from app.models import Batch, Job, JobEvent, JobStatus, TranscriptVersion
from app.schemas import (
    BatchCreateResponse,
    BatchDetailResponse,
    BatchResponse,
    DeleteJobResponse,
    DownloadFormatOption,
    JobCreateRequest,
    JobEventResponse,
    JobListResponse,
    JobResponse,
    PreviewRequest,
    PreviewResponse,
    SettingsResponse,
    SettingsUpdateRequest,
    TranscriptVersionResponse,
)
from app.services.jobs import add_job_event, create_batch, create_job, update_batch_status, update_job_status
from app.services import uploads as upload_svc

settings = get_settings()


class YouTubeURL(BaseModel):
    url: str


def _resolve_download_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser().resolve()
    downloads_root = Path(settings.downloads_dir).expanduser().resolve()
    if downloads_root not in candidate.parents and candidate != downloads_root:
        raise HTTPException(status_code=400, detail="File path is outside downloads directory")
    return candidate


def _fetch_preview_info(url: str) -> Dict[str, Any]:
    ydl = YoutubeDL({**_base_ydl_params(), "skip_download": True, "noplaylist": True})
    info = ydl.extract_info(url, download=False)
    if not isinstance(info, dict):
        raise ValueError("Unable to fetch preview metadata")
    return info


def _format_resolution(fmt: Dict[str, Any]) -> Optional[str]:
    if fmt.get("resolution"):
        return fmt.get("resolution")
    width = fmt.get("width")
    height = fmt.get("height")
    if width and height:
        return f"{width}x{height}"
    return None


def _build_format_options(info: Dict[str, Any]) -> List[DownloadFormatOption]:
    formats = info.get("formats") or []
    options: List[DownloadFormatOption] = []
    for fmt in formats:
        if not isinstance(fmt, dict):
            continue
        format_id = fmt.get("format_id")
        if not format_id:
            continue
        vcodec = fmt.get("vcodec")
        acodec = fmt.get("acodec")
        has_video = bool(vcodec and vcodec != "none")
        has_audio = bool(acodec and acodec != "none")
        options.append(
            DownloadFormatOption(
                format_id=str(format_id),
                ext=fmt.get("ext"),
                resolution=_format_resolution(fmt),
                width=fmt.get("width"),
                height=fmt.get("height"),
                fps=fmt.get("fps"),
                filesize=fmt.get("filesize"),
                filesize_approx=fmt.get("filesize_approx"),
                vcodec=vcodec,
                acodec=acodec,
                format_note=fmt.get("format_note"),
                tbr=fmt.get("tbr"),
                audio_channels=fmt.get("audio_channels"),
                has_audio=has_audio,
                has_video=has_video,
            )
        )
    return options


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="transcribeme - Queue to pt-BR", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        checks: dict = {"db": "ok", "redis": "ok"}
        status = "ok"
        try:
            from sqlalchemy import text as _text

            from app.db import SessionLocal as _SessionLocal

            with _SessionLocal() as _s:
                _s.execute(_text("SELECT 1"))
        except Exception as e:
            checks["db"] = f"error: {e}"
            status = "degraded"
        try:
            import redis as _redis

            _r = _redis.from_url(get_settings().redis_url, socket_timeout=2)
            _r.ping()
        except Exception as e:
            checks["redis"] = f"error: {e}"
            status = "degraded"
        return {"status": status, **checks}

    @app.get("/settings", response_model=SettingsResponse)
    def read_settings() -> SettingsResponse:
        s = get_settings()
        cookies_path = s.ytdlp_cookies_file
        cookies_configured = bool(cookies_path and Path(cookies_path).exists())
        return SettingsResponse(
            cookies_configured=cookies_configured,
            cookies_path=cookies_path,
            whisper_model=s.whisper_model,
            translation_target_lang_code=s.translation_target_lang_code,
            transcription_speed=s.transcription_speed,
            youtube_prefer_captions=s.youtube_prefer_captions,
            youtube_sub_langs=s.youtube_sub_langs,
        )

    @app.post("/settings", response_model=SettingsResponse)
    def update_settings(payload: SettingsUpdateRequest) -> SettingsResponse:
        updates = {k: v for k, v in payload.model_dump().items() if v is not None}
        # validate whisper_model already via pattern, validate lang code exists
        if "translation_target_lang_code" in updates:
            # basic validation: must be like xx_XXXX
            code = updates["translation_target_lang_code"]
            if len(code) < 4 or "_" not in code:
                raise HTTPException(status_code=400, detail="Invalid language code, expected like por_Latn")
        if "transcription_speed" in updates and updates["transcription_speed"] not in (1.0, 1.5):
            raise HTTPException(status_code=400, detail="transcription_speed must be 1.0 or 1.5")
        if "whisper_model" in updates and updates["whisper_model"] not in ("small", "medium", "large-v3"):
            raise HTTPException(status_code=400, detail="whisper_model must be small|medium|large-v3")
        s = save_settings(updates)
        cookies_path = s.ytdlp_cookies_file
        cookies_configured = bool(cookies_path and Path(cookies_path).exists())
        return SettingsResponse(
            cookies_configured=cookies_configured,
            cookies_path=cookies_path,
            whisper_model=s.whisper_model,
            translation_target_lang_code=s.translation_target_lang_code,
            transcription_speed=s.transcription_speed,
            youtube_prefer_captions=s.youtube_prefer_captions,
            youtube_sub_langs=s.youtube_sub_langs,
        )

    @app.post("/preview", response_model=PreviewResponse)
    def preview_formats(payload: PreviewRequest) -> PreviewResponse:
        try:
            info = _fetch_preview_info(payload.url)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if info.get("entries"):
            raise HTTPException(status_code=400, detail="Format preview is only supported for single video URLs.")
        formats = _build_format_options(info)
        return PreviewResponse(
            title=info.get("title"),
            uploader=info.get("uploader"),
            duration=info.get("duration"),
            webpage_url=info.get("webpage_url"),
            thumbnail=info.get("thumbnail"),
            formats=formats,
        )

    @app.post("/jobs", response_model=BatchCreateResponse, status_code=202)
    def create_jobs(request: JobCreateRequest, session: Session = Depends(get_session)) -> BatchCreateResponse:
        batch = create_batch(session, request.url)
        # optimistic Job so queue shows instantly, even while another job is processing
        job = create_job(session, source_url=request.url, batch_id=batch.id, video_url=request.url, title=request.url, uploader="YouTube", input_type="url", requested_format=request.format_id)
        add_job_event(session, job.id, "queued", "Queued for processing", 0.0)
        session.commit()
        enqueue_url.delay(batch.id, request.url, request.format_id, job.id)
        return BatchCreateResponse(batch_id=batch.id, message="Queued for processing")

    @app.post("/jobs/upload", response_model=JobResponse, status_code=202)
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
    @app.post("/uploads/init")
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

    @app.patch("/uploads/{upload_id}")
    async def upload_chunk(upload_id: str, request: Request) -> dict:
        data = await request.body()
        if not data:
            raise HTTPException(status_code=400, detail="Empty chunk")
        part = upload_svc.append_chunk(upload_id, data)
        size = part.stat().st_size
        return {"upload_id": upload_id, "received": size}

    @app.get("/uploads/{upload_id}/status")
    def upload_status(upload_id: str) -> dict:
        size = upload_svc.get_uploaded_size(upload_id)
        return {"upload_id": upload_id, "received": size}

    @app.post("/uploads/{upload_id}/complete", response_model=JobResponse, status_code=202)
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

    @app.post("/download_url", response_model=BatchCreateResponse, status_code=202)
    def legacy_download_url(payload: YouTubeURL, session: Session = Depends(get_session)) -> BatchCreateResponse:
        batch = create_batch(session, payload.url)
        session.commit()
        enqueue_url.delay(batch.id, payload.url, None)
        return BatchCreateResponse(batch_id=batch.id, message="Channel download started")

    @app.post("/process_untranscribed_videos", status_code=202)
    def legacy_process_untranscribed() -> dict:
        process_untranscribed_videos.delay(settings.downloads_dir)
        return {"message": "Processing untranscribed videos started"}

    @app.get("/jobs", response_model=JobListResponse)
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

    @app.get("/jobs/{job_id}", response_model=JobResponse)
    def get_job(job_id: str, session: Session = Depends(get_session)) -> JobResponse:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.post("/jobs/{job_id}/rerun", status_code=202)
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

    @app.post("/jobs/{job_id}/cancel", status_code=200)
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

    @app.delete("/jobs/{job_id}", response_model=DeleteJobResponse)
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
        # if neither specified, delete job only (keep files) ; if no query at all, legacy: keep files
        # But user wants checkboxes: they choose.
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

    @app.get("/jobs/{job_id}/events", response_model=List[JobEventResponse])
    def get_job_events(job_id: str, session: Session = Depends(get_session)) -> List[JobEventResponse]:
        events = session.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at.asc())).all()
        return events

    @app.get("/jobs/{job_id}/transcripts", response_model=List[TranscriptVersionResponse])
    def list_transcripts(job_id: str, session: Session = Depends(get_session)) -> List[TranscriptVersionResponse]:
        job = session.get(Job, job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        versions = session.scalars(select(TranscriptVersion).where(TranscriptVersion.job_id == job_id).order_by(TranscriptVersion.version.asc())).all()
        return versions

    @app.get("/jobs/{job_id}/transcript/{version}")
    def get_transcript_version(job_id: str, version: int, session: Session = Depends(get_session)) -> PlainTextResponse:
        tv = session.scalar(select(TranscriptVersion).where(TranscriptVersion.job_id == job_id, TranscriptVersion.version == version))
        if not tv:
            raise HTTPException(status_code=404, detail="Version not found")
        path = _resolve_download_path(tv.transcript_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Transcript file not found")
        return PlainTextResponse(path.read_text(encoding="utf-8", errors="ignore"))

    @app.delete("/jobs/{job_id}/transcript/{version}")
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

    @app.get("/jobs/{job_id}/media")
    def get_job_media(job_id: str, session: Session = Depends(get_session)) -> FileResponse:
        job = session.get(Job, job_id)
        if not job or not job.download_path:
            raise HTTPException(status_code=404, detail="Media file not found")
        media_path = _resolve_download_path(job.download_path)
        if not media_path.exists():
            raise HTTPException(status_code=404, detail="Media file not found")
        media_type, _ = mimetypes.guess_type(media_path.name)
        return FileResponse(media_path, media_type=media_type or "application/octet-stream", filename=media_path.name)

    @app.get("/jobs/{job_id}/transcript")
    def get_job_transcript(job_id: str, session: Session = Depends(get_session)) -> PlainTextResponse:
        job = session.get(Job, job_id)
        if not job or not job.transcript_path:
            raise HTTPException(status_code=404, detail="Transcript not found")
        transcript_path = _resolve_download_path(job.transcript_path)
        if not transcript_path.exists():
            raise HTTPException(status_code=404, detail="Transcript not found")
        transcript_text = transcript_path.read_text(encoding="utf-8", errors="ignore")
        return PlainTextResponse(transcript_text)

    @app.get("/batches", response_model=List[BatchResponse])
    def list_batches(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0), session: Session = Depends(get_session)) -> List[BatchResponse]:
        batches = session.scalars(select(Batch).order_by(Batch.created_at.desc()).limit(limit).offset(offset)).all()
        return batches

    @app.get("/batches/{batch_id}", response_model=BatchDetailResponse)
    def get_batch(batch_id: str, session: Session = Depends(get_session)) -> BatchDetailResponse:
        batch = session.get(Batch, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        jobs = session.scalars(select(Job).where(Job.batch_id == batch_id)).all()
        return BatchDetailResponse(batch=batch, jobs=jobs, total=len(jobs))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
