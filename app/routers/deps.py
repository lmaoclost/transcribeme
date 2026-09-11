"""Shared controller dependencies: settings snapshot + guarded path resolution."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.config import get_settings

settings = get_settings()


def resolve_download_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser().resolve()
    downloads_root = Path(settings.downloads_dir).expanduser().resolve()
    if downloads_root not in candidate.parents and candidate != downloads_root:
        raise HTTPException(status_code=400, detail="File path is outside downloads directory")
    return candidate


# backward-compat alias (tests + jobs router patch target)
_resolve_download_path = resolve_download_path
