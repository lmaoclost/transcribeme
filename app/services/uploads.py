"""Chunked upload handling for resumable 5MB chunks."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from app.config import get_settings

settings = get_settings()

ALLOWED_EXTS = {".mp4", ".mp3"}

def get_uploads_dir() -> Path:
    p = Path(settings.downloads_dir) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p

def get_upload_path(upload_id: str) -> Path:
    return get_uploads_dir() / f"{upload_id}.part"

def get_final_path(original_filename: str, upload_id: str) -> Path:
    ext = Path(original_filename).suffix.lower()
    # sanitize
    safe = "".join(c for c in Path(original_filename).stem if c.isalnum() or c in "-_ ")[:100]
    if not safe:
        safe = "upload"
    # store under downloads/uploads or downloads directly? use downloads/{uploader}/upload...
    # For now, downloads/uploads/{id}_{safe}{ext}
    return get_uploads_dir() / f"{upload_id}_{safe}{ext}"

def is_allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTS

def append_chunk(upload_id: str, data: bytes) -> Path:
    part = get_upload_path(upload_id)
    with open(part, "ab") as f:
        f.write(data)
    return part

def get_uploaded_size(upload_id: str) -> int:
    part = get_upload_path(upload_id)
    if not part.exists():
        return 0
    return part.stat().st_size

def finalize_upload(upload_id: str, original_filename: str) -> Path:
    part = get_upload_path(upload_id)
    final = get_final_path(original_filename, upload_id)
    if not part.exists():
        raise FileNotFoundError("upload not found")
    part.rename(final)
    return final
