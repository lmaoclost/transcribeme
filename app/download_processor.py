"""Download and enqueue YouTube videos."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery.signals import worker_process_init
from celery.utils.log import get_task_logger
from yt_dlp import YoutubeDL

from app.celery_app import celery_app
from app.config import get_settings
from app import db
from app.models import BatchStatus, InputType, Job, JobStatus, TranscriptVersion
from app.services.jobs import (
    add_job_event,
    create_job,
    set_batch_status,
    update_batch_status,
    update_job_status,
)
from sqlalchemy import func

logger = get_task_logger(__name__)

INFO_YDL: Optional[YoutubeDL] = None


class DownloadProcessorLogger:
    def debug(self, msg):
        if msg.startswith("[debug] "):
            logger.debug(msg)
        else:
            self.info(msg)

    def info(self, msg):
        logger.info(msg)

    def warning(self, msg):
        logger.warning(msg)

    def error(self, msg):
        logger.error(msg)


def _is_direct_media_url(url: str) -> bool:
    low = url.lower().split("?")[0]
    return low.endswith((".mp4", ".mp3", ".m4a", ".webm", ".mkv", ".wav", ".ogg", ".mov"))

def _base_ydl_params() -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "logger": DownloadProcessorLogger(),
        "format": "best",
        "noplaylist": True,
        "extractor_retries": 3,
        "fragment_retries": 3,
        "retries": 3,
        "sleep_interval": 1,
        "max_sleep_interval": 5,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        },
        "socket_timeout": 30,
        "ignoreerrors": False,
        "no_warnings": False,
    }
    return params


@worker_process_init.connect
def init_worker_processes(**kwargs) -> None:
    """Initialize shared YoutubeDL instance per worker process."""
    global INFO_YDL
    logger.info("init download processor")
    info_params = {**_base_ydl_params(), "skip_download": True, "noplaylist": False}
    info_params.pop("format", None)
    INFO_YDL = YoutubeDL(info_params)


def extract_yt_info(yt_url: str) -> Dict[str, Any]:
    """Get metadata from a YouTube URL."""
    if INFO_YDL is None:
        raise RuntimeError("YoutubeDL is not initialized")

    logger.info('Getting info for URL "%s"', yt_url)
    yt_info = INFO_YDL.extract_info(yt_url, download=False, process=True)
    if not isinstance(yt_info, dict):
        raise ValueError("Unknown type of yt_info")
    return yt_info


def _safe_entries(info: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = info.get("entries")
    if not entries:
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _create_output_dir(uploader: str) -> Path:
    base = Path(get_settings().downloads_dir)
    target = base / uploader
    target.mkdir(parents=True, exist_ok=True)
    return target


@celery_app.task(name="app.download_processor.enqueue_url")
def enqueue_url(batch_id: str, url: str, requested_format: Optional[str] = None, job_id: Optional[str] = None) -> None:
    """Resolve a URL into one or more jobs and enqueue downloads. Supports YouTube + direct media URLs. Optimistic job_id reused if provided."""
    logger.info("Enqueueing URL %s (optimistic job %s)", url, job_id)
    # Direct media URL: skip yt-dlp info
    if _is_direct_media_url(url):
        with db.SessionLocal() as session:
            output_dir = _create_output_dir("direct")
            if job_id:
                job = session.get(Job, job_id)
                if job:
                    job.video_url = url
                    job.title = url.split("/")[-1].split("?")[0]
                    job.uploader = "direct"
                    job.input_type = InputType.direct_url
                    session.add(job)
                    session.commit()
                else:
                    job = create_job(session, source_url=url, batch_id=batch_id, video_url=url, title=url.split("/")[-1].split("?")[0], uploader="direct", requested_format=requested_format, input_type="direct_url")
                    add_job_event(session, job.id, "queued", "Queued for download", 0.0)
                    session.commit()
            else:
                job = create_job(session, source_url=url, batch_id=batch_id, video_url=url, title=url.split("/")[-1].split("?")[0], uploader="direct", requested_format=requested_format, input_type="direct_url")
                add_job_event(session, job.id, "queued", "Queued for download", 0.0)
                session.commit()
            download_video.apply_async(args=[job.id, url, str(output_dir)], queue="download_queue")
            update_batch_status(session, batch_id)
            session.commit()
        return

    try:
        yt_info = extract_yt_info(url)
    except Exception as exc:
        logger.error("Failed to extract info for %s: %s", url, exc)
        with db.SessionLocal() as session:
            set_batch_status(session, batch_id, status=BatchStatus.failed)
            if job_id:
                job = session.get(Job, job_id)
                if job:
                    update_job_status(session, job, JobStatus.failed, error=str(exc))
                    add_job_event(session, job.id, "failed", f"Failed to extract info: {exc}")
            session.commit()
            update_batch_status(session, batch_id)
            session.commit()
        raise

    with db.SessionLocal() as session:
        if "entries" in yt_info:
            uploader = yt_info.get("uploader", "Unknown")
            output_dir = _create_output_dir(uploader)
            entries = _safe_entries(yt_info)
            for idx, entry in enumerate(entries):
                video_id = entry.get("id")
                title = entry.get("title")
                video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else None
                if idx == 0 and job_id:
                    job = session.get(Job, job_id)
                    if job:
                        job.video_id = video_id
                        job.title = title
                        job.video_url = video_url
                        job.uploader = uploader
                        session.add(job)
                        add_job_event(session, job.id, "queued", "Queued for download", 0.0)
                        session.commit()
                    else:
                        job = create_job(session, source_url=url, batch_id=batch_id, video_url=video_url, video_id=video_id, title=title, uploader=uploader, requested_format=requested_format, input_type="url")
                        add_job_event(session, job.id, "queued", "Queued for download", 0.0)
                        session.commit()
                else:
                    job = create_job(session, source_url=url, batch_id=batch_id, video_url=video_url, video_id=video_id, title=title, uploader=uploader, requested_format=requested_format, input_type="url")
                    add_job_event(session, job.id, "queued", "Queued for download", 0.0)
                    session.commit()
                if video_url:
                    download_video.apply_async(args=[job.id, video_url, str(output_dir)], queue="download_queue")
        else:
            video_id = yt_info.get("id")
            uploader = yt_info.get("uploader", "Unknown")
            title = yt_info.get("title")
            output_dir = _create_output_dir(uploader)
            # Try YouTube captions first (even auto), fallback to whisper
            _s = get_settings()
            if _s.youtube_prefer_captions:
                try:
                    from app.services.youtube_captions import fetch_youtube_transcript
                    from app.services.translation import translate as translate_to_pt_br

                    cap = fetch_youtube_transcript(url)
                    if cap:
                        raw_text, cap_lang = cap
                        tgt_code = _s.translation_target_lang_code
                        # decide skip if src matches target
                        src_short = (cap_lang or "").lower()[:2]
                        tgt_short = tgt_code.split("_")[0][:2].lower() if "_" in tgt_code else tgt_code[:2].lower()
                        prefix_map = {"por": "pt", "eng": "en", "spa": "es", "fra": "fr", "deu": "de"}
                        tgt_as_short = prefix_map.get(tgt_code.split("_")[0].lower()[:3], tgt_short)
                        needs_tr = not (src_short and src_short == tgt_as_short)
                        pt_text = translate_to_pt_br(raw_text, cap_lang, tgt_code) if needs_tr else raw_text
                        # reuse optimistic job if provided
                        if job_id:
                            job = session.get(Job, job_id)
                            if job:
                                job.video_id = video_id
                                job.title = title
                                job.video_url = url
                                job.uploader = uploader
                                job.source_lang = cap_lang
                                session.add(job)
                            else:
                                job = create_job(session, source_url=url, batch_id=batch_id, video_url=url, video_id=video_id, title=title, uploader=uploader, requested_format=requested_format, input_type="url")
                                job.source_lang = cap_lang
                                session.add(job)
                        else:
                            job = create_job(session, source_url=url, batch_id=batch_id, video_url=url, video_id=video_id, title=title, uploader=uploader, requested_format=requested_format, input_type="url")
                            job.source_lang = cap_lang
                            session.add(job)
                        # write plain transcript (no timestamps) like .mp4 path
                        safe_title = "".join(c for c in (title or video_id or job.id) if c.isalnum() or c in " -_")[:50].strip() or video_id or job.id
                        transcript_path = str(output_dir / f"{safe_title}-{video_id or job.id[:8]}.captions.txt")
                        Path(transcript_path).write_text(pt_text, encoding="utf-8")
                        # versioning
                        tv = TranscriptVersion(job_id=job.id, version=1, transcript_path=transcript_path, model_name="caption", source_lang=cap_lang)
                        session.add(tv)
                        update_job_status(session, job, JobStatus.completed, progress=100.0, transcript_path=transcript_path)
                        add_job_event(session, job.id, "completed", f"Captions fetched v1 lang={cap_lang}->{tgt_code}" if needs_tr else f"Captions fetched v1 lang={cap_lang}", 100.0)
                        session.commit()
                        update_batch_status(session, batch_id)
                        session.commit()
                        logger.info("YouTube captions used for %s lang=%s", url, cap_lang)
                        return
                except Exception as e:
                    logger.warning("Caption fetch failed for %s, falling back to download: %s", url, e)
            if job_id:
                job = session.get(Job, job_id)
                if job:
                    job.video_id = video_id
                    job.title = title
                    job.video_url = url
                    job.uploader = uploader
                    session.add(job)
                    session.commit()
                else:
                    job = create_job(session, source_url=url, batch_id=batch_id, video_url=url, video_id=video_id, title=title, uploader=uploader, requested_format=requested_format, input_type="url")
                    add_job_event(session, job.id, "queued", "Queued for download", 0.0)
                    session.commit()
            else:
                job = create_job(session, source_url=url, batch_id=batch_id, video_url=url, video_id=video_id, title=title, uploader=uploader, requested_format=requested_format, input_type="url")
                add_job_event(session, job.id, "queued", "Queued for download", 0.0)
                session.commit()
            download_video.apply_async(args=[job.id, url, str(output_dir)], queue="download_queue")

        update_batch_status(session, batch_id)
        session.commit()


@celery_app.task(bind=True, name="app.download_processor.download_video")
def download_video(self, job_id: str, url: str, output_dir: str) -> None:
    """Download a video and enqueue transcription."""
    logger.info("Downloading %s to %s", url, output_dir)
    with db.SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        update_job_status(session, job, JobStatus.downloading, progress=0.0)
        add_job_event(session, job.id, "downloading", "Download started", 0.0)
        session.commit()

        last_progress = 0.0

        def progress_hook(data: Dict[str, Any]) -> None:
            nonlocal last_progress
            if data.get("status") == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                downloaded = data.get("downloaded_bytes")
                if total and downloaded:
                    pct = (downloaded / total) * 100
                    overall = min(50.0, pct * 0.5)
                    if overall - last_progress >= 1.0:
                        job.progress = overall
                        job.updated_at = datetime.now(timezone.utc)
                        session.add(job)
                        session.commit()
                        last_progress = overall
            elif data.get("status") == "finished":
                filename = data.get("filename")
                if filename:
                    update_job_status(
                        session,
                        job,
                        JobStatus.downloaded,
                        progress=50.0,
                        download_path=filename,
                    )
                    add_job_event(session, job.id, "downloaded", "Download finished", 50.0)
                    session.commit()

        try:
            if _is_direct_media_url(url):
                try:
                    ydl = YoutubeDL(
                        {
                            **_base_ydl_params(),
                            "format": "bv*+ba/b",
                            "outtmpl": f"{output_dir}/%(title).200B-%(id)s.%(ext)s",
                            "progress_hooks": [progress_hook],
                        }
                    )
                    ydl.download([url])
                except Exception:
                    # fallback: http stream
                    import requests

                    filename = Path(output_dir) / (url.split("/")[-1].split("?")[0] or f"{job.id}.mp4")
                    filename.parent.mkdir(parents=True, exist_ok=True)
                    with requests.get(url, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(filename, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    f.write(chunk)
                    update_job_status(session, job, JobStatus.downloaded, progress=50.0, download_path=str(filename))
                    add_job_event(session, job.id, "downloaded", "Download finished", 50.0)
                    session.commit()
                    from app.transcription_processor import transcribe_video

                    transcribe_video.apply_async(args=[job.id], queue="transcription_queue")
                    return
            else:
                format_id = job.requested_format or "bv*+ba/b"
                ydl = YoutubeDL(
                    {
                        **_base_ydl_params(),
                        "format": format_id,
                        "outtmpl": f"{output_dir}/%(title).200B-%(id)s.%(ext)s",
                        "progress_hooks": [progress_hook],
                    }
                )
                ydl.download([url])
        except Exception as exc:
            logger.error("Failed to download %s: %s", url, exc)
            update_job_status(session, job, JobStatus.failed, error=str(exc))
            add_job_event(session, job.id, "failed", f"Download failed: {exc}")
            session.commit()
            if job.batch_id:
                update_batch_status(session, job.batch_id)
                session.commit()
            return

        from app.transcription_processor import transcribe_video

        transcribe_video.apply_async(args=[job.id], queue="transcription_queue")
