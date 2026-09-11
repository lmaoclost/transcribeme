"""POST /preview (format picker)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from yt_dlp import YoutubeDL

from app.download_processor import _base_ydl_params
from app.schemas import DownloadFormatOption, PreviewRequest, PreviewResponse

router = APIRouter()


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


@router.post("/preview", response_model=PreviewResponse)
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
