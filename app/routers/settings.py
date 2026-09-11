"""GET/POST /settings (Options modal persistence)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.config import get_settings, save_settings
from app.schemas import SettingsResponse, SettingsUpdateRequest

router = APIRouter()


def _to_response(s) -> SettingsResponse:
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


@router.get("/settings", response_model=SettingsResponse)
def read_settings() -> SettingsResponse:
    return _to_response(get_settings())


@router.post("/settings", response_model=SettingsResponse)
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
    return _to_response(save_settings(updates))
