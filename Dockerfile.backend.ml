# ML runtime: transcription worker only. Extends slim with CPU-only torch + faster-whisper + NLLB.
ARG SLIM_IMAGE=ghcr.io/lmaoclost/transcribeme-backend-slim:latest
FROM ${SLIM_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# CPU-only torch wheels (~150MB) instead of default CUDA bundle (~2.5GB)
RUN uv pip install --system --no-cache-dir --compile-bytecode \
    --index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.2.0" && \
    uv pip install --system --no-cache-dir --compile-bytecode \
    ".[ml]"

CMD ["celery", "-A", "app.celery_app.celery_app", "worker", "-Q", "transcription_queue", "--loglevel=info", "--concurrency=1"]
