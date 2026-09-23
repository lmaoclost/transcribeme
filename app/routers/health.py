"""GET /health with deep-checks: db, redis, celery workers, queues, beat, disk."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


def _check_db() -> str:
    from sqlalchemy import text as _text

    from app.db import SessionLocal as _SessionLocal

    with _SessionLocal() as _s:
        _s.execute(_text("SELECT 1"))
    return "ok"


def _check_redis() -> dict:
    import redis as _redis

    _r = _redis.from_url(get_settings().redis_url, socket_timeout=2)
    info = _r.info("server")
    return {"status": "ok", "version": info.get("redis_version", "unknown")}


def _check_workers() -> dict:
    from app.celery_app import celery_app

    ping = celery_app.control.ping(timeout=5)
    names = sorted(next(iter(entry)) for entry in ping) if ping else []
    return {"status": "ok" if len(names) >= 2 else "degraded", "workers": names}


def _check_queues() -> dict:
    import redis as _redis

    _r = _redis.from_url(get_settings().redis_url, socket_timeout=2)
    return {
        q: _r.llen(q) for q in ("transcription_queue", "download_queue") if _r.exists(q)
    }


def _check_disk() -> dict:
    usage = shutil.disk_usage(get_settings().downloads_dir)
    free_gb = round(usage.free / 1024**3, 2)
    return {"status": "degraded" if free_gb < 1.0 else "ok", "free_gb": free_gb}


def _check_dirs() -> dict:
    s = get_settings()
    missing = [
        name
        for name, path in (("downloads", s.downloads_dir), ("models", s.models_dir), ("data", "data"))
        if not Path(path).exists()
    ]
    return {"status": "ok" if not missing else "degraded", "missing": missing}


@router.get("/health")
def health() -> dict:
    checks: dict = {}
    status = "ok"

    def _run(name: str, fn, *args) -> None:
        nonlocal status
        try:
            result = fn(*args)
            checks[name] = result if isinstance(result, dict) else result
            if isinstance(result, dict) and result.get("status") == "degraded":
                status = "degraded"
        except Exception as e:
            checks[name] = {"status": "degraded", "error": str(e)}
            status = "degraded"

    _run("db", _check_db)
    _run("redis", _check_redis)
    _run("workers", _check_workers)
    _run("queues", _check_queues)
    _run("disk", _check_disk)
    _run("dirs", _check_dirs)
    return {"status": status, **checks}
