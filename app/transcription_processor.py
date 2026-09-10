"""Transcription worker tasks."""

from __future__ import annotations

from pathlib import Path

from celery.signals import worker_process_init
from celery.utils.log import get_task_logger

from app.celery_app import celery_app
from app.config import get_settings
from app import db
from app.models import Job, JobStatus
from sqlalchemy import func, select

from app.services.jobs import add_job_event, create_job, update_batch_status, update_job_status
from app.whisper_transcriber import WhisperTranscriber
from app.models import TranscriptVersion
from app.audio_tools import accelerate_audio, split_audio_for_transcription
from app.services.translation import translate as translate_to_pt_br, needs_translation

logger = get_task_logger(__name__)
settings = get_settings()


@worker_process_init.connect
def init_transcriber(**kwargs):
    transcribe_video.transcriber = WhisperTranscriber()


@celery_app.task(bind=True, name="app.transcription_processor.transcribe_video")
def transcribe_video(self, job_id: str) -> None:
    """Translate the downloaded video to pt-BR."""
    with db.SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            logger.error("Job %s not found", job_id)
            return

        if not job.download_path:
            update_job_status(session, job, JobStatus.failed, error="Missing download path")
            add_job_event(session, job.id, "failed", "Missing download path")
            session.commit()
            return

        update_job_status(session, job, JobStatus.transcribing, progress=60.0)
        add_job_event(session, job.id, "transcribing", "Transcription started (whisper small)", 60.0)
        session.commit()

        try:
            audio_path = Path(job.download_path)
            # Global acceleration 1.5x (applies to all lengths) — atempo pitch-preserving
            factor = float(settings.transcription_speed) if settings.transcription_speed else 1.5
            if factor not in (1.0, 1.5):
                factor = 1.5
            acc_base: Path | None = None
            if factor != 1.0:
                logger.info("Accelerating audio %.1fx", factor)
                add_job_event(session, job.id, "accelerating", f"Accelerating audio {factor}x", 58.0)
                session.commit()
                acc_base = accelerate_audio(audio_path, factor)
                # use accelerated path for transcription (split handles temp)
                transcribe_path = acc_base
            else:
                transcribe_path = audio_path

            # Transcribe (auto-detect lang), then translate to pt-BR if needed via NLLB
            def _do_transcribe(p: Path) -> tuple[str, str | None]:
                txt, lng = self.transcriber.transcribe_audio(p)
                return txt, lng

            if WhisperTranscriber.needs_splitting(transcribe_path, settings.splitter_threshold_minutes):
                chunks = split_audio_for_transcription(transcribe_path, settings.splitter_chunk_minutes)
                raw_texts = []
                detected_lang = None
                for chunk in chunks:
                    t, lang = _do_transcribe(chunk)
                    raw_texts.append(t)
                    if lang and not detected_lang:
                        detected_lang = lang
                    if chunk != transcribe_path and chunk.exists():
                        try:
                            chunk.unlink()
                        except Exception:
                            pass
                raw_transcription = "\n".join(raw_texts)
                lang = detected_lang
            else:
                raw_transcription, lang = _do_transcribe(transcribe_path)

            # cleanup accelerated temp (if not already cleaned as chunk source)
            if acc_base is not None and acc_base != audio_path and acc_base.exists():
                try:
                    acc_base.unlink()
                except Exception:
                    pass

            # Translate to pt-BR if needed
            if needs_translation(lang):
                logger.info("Translating %s -> pt-BR via NLLB", lang)
                add_job_event(session, job.id, "translating", f"Translating {lang} -> pt-BR", 85.0)
                session.commit()
                transcription = translate_to_pt_br(raw_transcription, lang)
            else:
                transcription = raw_transcription
                logger.info("Source is pt (%s), skipping translation", lang)

            # Versioning: keep old
            existing_count = session.scalar(
                select(func.count()).select_from(TranscriptVersion).where(TranscriptVersion.job_id == job.id)
            ) or 0
            version = existing_count + 1
            # Save with version suffix after first
            if version == 1:
                transcript_path = f"{job.download_path}.txt"
            else:
                transcript_path = f"{job.download_path}.v{version}.txt"
            with open(transcript_path, "w", encoding="utf-8") as handle:
                handle.write(transcription)

            # store version
            tv = TranscriptVersion(
                job_id=job.id, version=version, transcript_path=transcript_path,
                model_name=settings.whisper_model, source_lang=lang
            )
            session.add(tv)
            # update job
            update_job_status(
                session, job, JobStatus.completed, progress=100.0, transcript_path=transcript_path
            )
            if lang:
                job.source_lang = lang
                session.add(job)
            add_job_event(session, job.id, "completed", f"Transcription+translation completed v{version} lang={lang}->pt-BR", 100.0)
            session.commit()
            if job.batch_id:
                update_batch_status(session, job.batch_id)
                session.commit()
        except Exception as exc:
            logger.error("Transcription failed for %s: %s", job_id, exc)
            update_job_status(session, job, JobStatus.failed, error=str(exc))
            add_job_event(session, job.id, "failed", f"Transcription failed: {exc}")
            session.commit()
            if job.batch_id:
                update_batch_status(session, job.batch_id)
                session.commit()


def find_untranscribed_videos(directory: Path) -> list[Path]:
    """Find mp4 files with no matching txt transcript."""
    untranscribed = []
    for video_path in directory.glob("**/*.mp4"):
        txt_path = video_path.with_name(video_path.name + ".txt")
        if not txt_path.exists():
            untranscribed.append(video_path)
    return untranscribed


@celery_app.task(name="app.transcription_processor.process_untranscribed_videos")
def process_untranscribed_videos(directory: str | None = None) -> None:
    """Queue transcription jobs for any downloaded videos missing transcripts."""
    target_dir = Path(directory or settings.downloads_dir)
    untranscribed = find_untranscribed_videos(target_dir)
    logger.info("Found %s untranscribed videos", len(untranscribed))

    with db.SessionLocal() as session:
        for video_path in untranscribed:
            existing = session.scalar(
                select(Job).where(Job.download_path == str(video_path))
            )
            if existing:
                continue
            job = create_job(session, source_url="local", video_url=None)
            update_job_status(session, job, JobStatus.downloaded, progress=50.0, download_path=str(video_path))
            add_job_event(session, job.id, "downloaded", "Imported local download", 50.0)
            session.commit()
            transcribe_video.apply_async(args=[job.id], queue="transcription_queue")
