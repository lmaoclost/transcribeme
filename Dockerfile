FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md /app/
COPY app /app/app

# dev needs ML stack too (transcription worker); CPU-only torch for local i5
RUN uv pip install --system --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch>=2.2.0" && \
    uv pip install --system --no-cache-dir ".[ml]"

COPY . /app/

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
