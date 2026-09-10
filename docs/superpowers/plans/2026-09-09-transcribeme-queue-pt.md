# transcribeme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Queue YouTube link / direct media URL / mp4|mp3 upload -> translate to pt-BR via faster-whisper small int8 CPU, view/delete/rerun via Web UI + API, runs on ZimaOS i5-7200U 16GB.

**Architecture:** Fork queuetube-whisper-transcriber. Add file ingress (chunked 5MB resumable) + direct media URL handling. Switch whisper task to translate to pt-BR with ffmpeg chunk splitter for unlimited length. Keep FIFO 1 concurrency. Transcript versioning table. Cron cleanup 7d. Polling Next.js UI (single form URL+drag-drop, modal versions).

**Tech Stack:** Python 3.11 FastAPI + Celery + Redis + SQLite + faster-whisper + yt-dlp + ffmpeg + Next.js 15 + Docker Compose

## Global Constraints
- CPU only, device=cpu compute_type=int8
- i5-7200U 2c/4t 16GB concurrency 1 per queue
- No auth (local)
- Input: YouTube (A) + direct media URL (C) + mp4/mp3 upload chunked 5MB
- Playlist => N jobs
- Whisper model small int8 lazy pull, task=translate pt-BR, detect source lang
- Output txt only, pt-BR
- Volumes configurable via compose env HOST_DOWNLOADS etc
- Auto-cleanup 7d
- Keep OpenAPI /docs
- Single delete with checkboxes (media/transcript), rerun versions modal keep old

---

### Task 1: Scaffold fork base

**Files:**
- Create: `app/*`, `frontend/*` from queuetube, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `data/`, `downloads/`, `models/`
- Modify: `app/config.py` (add env), `docker-compose.yml` (parametrized volumes), `README.md`

**Steps:**
- [ ] Clone queuetube files into worktree
- [ ] Strip deno/cookies optional, keep ffmpeg
- [ ] docker-compose with ${HOST_DOWNLOADS:-./downloads} etc, use docker compose

### Task 2: Data model with TranscriptVersion

**Files:** app/models.py, app/schemas.py, app/db.py

**Steps:**
- [ ] Add TranscriptVersion table + Job.input_type enum + Job.original_filename
- [ ] Add JobStatus.canceled handling
- [ ] Migration auto create via init_db()

### Task 3: Direct URL + chunked upload 5MB

**Files:** app/services/uploads.py, app/api.py, app/download_processor.py

**Steps:**
- [ ] POST /jobs multipart url OR file, PATCH /uploads/{id} chunk handling
- [ ] Handle direct mp4/mp3 URL via yt-dlp generic or http download
- [ ] Tests: upload 10MB resume

### Task 4-5: Translate + splitter + versioning/rerun/cancel

**Files:** app/audio_tools.py, app/whisper_transcriber.py, app/transcription_processor.py, app/api.py

**Steps:**
- [ ] Switch transcribe_audio to task=translate
- [ ] Add ffmpeg splitter >30min -> 20min chunks
- [ ] TranscriptVersion creation + POST /jobs/{id}/rerun + POST /jobs/{id}/cancel

### Task 6: Delete granularity + 7d cleanup

**Files:** app/api.py, app/tasks/cleanup.py

**Steps:**
- [ ] DELETE /jobs/{id}?purge_media&purge_transcript flags + version delete
- [ ] Celery beat daily cleanup

### Task 7-8: API + Next.js polling UI

**Files:** frontend/app/*, frontend/components/*

**Steps:**
- [ ] Single form URL+drag-drop, polling 2.5s, modal versions, checkboxes delete

### Task 9: Docker/ZimaOS packaging

**Files:** docker-compose.yml, Dockerfile, README

**Steps:**
- [ ] Verify docker compose up, docs
