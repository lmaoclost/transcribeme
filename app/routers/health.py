"""GET /health with DB + redis deep-checks."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter()


@router.get("/health")
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
