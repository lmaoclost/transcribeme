"""Legacy endpoints (backward compat): /download_url, /process_untranscribed_videos."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.download_processor import enqueue_url
from app.routers.deps import settings
from app.schemas import BatchCreateResponse
from app.services.jobs import create_batch
from app.transcription_processor import process_untranscribed_videos

router = APIRouter()


class YouTubeURL(BaseModel):
    url: str


@router.post("/download_url", response_model=BatchCreateResponse, status_code=202)
def legacy_download_url(payload: YouTubeURL, session: Session = Depends(get_session)) -> BatchCreateResponse:
    batch = create_batch(session, payload.url)
    session.commit()
    enqueue_url.delay(batch.id, payload.url, None)
    return BatchCreateResponse(batch_id=batch.id, message="Channel download started")


@router.post("/process_untranscribed_videos", status_code=202)
def legacy_process_untranscribed() -> dict:
    process_untranscribed_videos.delay(settings.downloads_dir)
    return {"message": "Processing untranscribed videos started"}
