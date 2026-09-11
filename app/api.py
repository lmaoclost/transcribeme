"""FastAPI server for transcribeme - YouTube + direct URL + upload queue with translate to pt-BR.

MVC layout: this module only wires the app (middleware + lifespan + routers).
Controllers live in app.routers.*, domain logic in app.services.*, data in
app.models (DB) + app.schemas (DTOs).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers import batches, health, jobs, legacy, preview, settings, uploads
from app.routers.deps import settings as _settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="transcribeme - Queue to pt-BR", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(settings.router)
    app.include_router(preview.router)
    app.include_router(uploads.router)
    app.include_router(jobs.router)
    app.include_router(batches.router)
    app.include_router(legacy.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
