# transcribeme

Queue YouTube / direct media URL / mp4·mp3 upload → translate to **pt-BR** with `faster-whisper` `small` (CPU `int8`). FIFO single-concurrency, made for **ZimaOS** / i5-7200U 16GB.

Fork of [queuetube-whisper-transcriber](https://github.com/seandearnaley/queuetube-whisper-transcriber) with:
- **Direct URL** support (`*.mp4`, `*.mp3`, etc) via yt-dlp generic + http fallback
- **File upload** `mp4`/`mp3` via single `POST /jobs/upload` or chunked resumable `POST /uploads/init` + `PATCH /uploads/{id}` (5MB chunks) + `POST /uploads/{id}/complete`
- **Translate** task: `faster-whisper` `task=translate` → pt-BR, lang detection via `info.language`, stored as `source_lang`
- **Unlimited length**: ffmpeg split >30min into 20min chunks → translate → concat
- **Versioning**: each rerun keeps old transcript as `TranscriptVersion` (`.v2.txt` etc), modal list in UI
- **Delete granularity**: `DELETE /jobs/{id}?purge_media=true&purge_transcript=true` (checkboxes in UI) + `DELETE /jobs/{id}/transcript/{version}`
- **Rerun**: `POST /jobs/{id}/rerun` (re-transcribe same media, new version) + `POST /jobs/{id}/cancel` (queued/downloading only)
- **Cleanup**: Celery beat daily at 03:00 UTC removes jobs older than `QTUBE_CLEANUP_DAYS` (default 7) and unlinks files (respects `downloads` root jail)
- **Polling UI**: Next.js 15, single form URL + drag&drop, polling 2.5s, versions modal
- **Compose**: `docker compose` with configurable volumes `HOST_DOWNLOADS_DIR`, `HOST_DATA_DIR`, `HOST_MODELS_DIR`, `QTUBE_WHISPER_MODEL=small`, `QTUBE_CLEANUP_DAYS=7`

## Quick start (ZimaOS / any Docker)

```bash
# configure host paths if needed (ZimaOS: point to your NAS share)
export HOST_DOWNLOADS_DIR=./downloads
export HOST_DATA_DIR=./data
export HOST_MODELS_DIR=./models
export QTUBE_WHISPER_MODEL=small   # small|medium (medium slower but better PT)
docker compose up --build -d
# services:
#  API:        http://localhost:8000  (OpenAPI /docs)
#  Frontend:   http://localhost:3000
#  Redis:      6379
```

## API (OpenAPI at /docs)

- `POST /jobs` `{url, format_id?}` → 202 batch (YouTube or direct mp4/mp3)
- `POST /jobs/upload` multipart `file` (mp4/mp3) → 202 job
- `POST /uploads/init?filename=&total_size=` → `{upload_id}`
- `PATCH /uploads/{id}` body chunk → `{received}`
- `POST /uploads/{id}/complete?filename=` → 202 job
- `GET /jobs?status=&batch_id=&limit=&offset=` + `GET /jobs/{id}` + `GET /jobs/{id}/events`
- `GET /jobs/{id}/media` + `GET /jobs/{id}/transcript` + `GET /jobs/{id}/transcripts` + `GET /jobs/{id}/transcript/{version}`
- `POST /jobs/{id}/rerun` + `POST /jobs/{id}/cancel`
- `DELETE /jobs/{id}?purge_media=&purge_transcript=` + `DELETE /jobs/{id}/transcript/{version}`
- `GET /batches` + `GET /batches/{id}` + `GET /health` + `GET /settings` + `POST /preview`

Example:

```bash
curl -X POST http://localhost:8000/jobs -H "Content-Type: application/json" -d '{"url":"https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
curl -X POST http://localhost:8000/jobs/upload -F file=@video.mp4
# chunked
CID=$(curl -s -X POST "http://localhost:8000/uploads/init?filename=big.mp4&total_size=123456" | jq -r .upload_id)
# PATCH loop 5MB then complete
```

## Hardware

- Default `small` int8: ~1.3GB RAM transcribing, fits 16GB. `medium` ~2.2GB (better pt-BR, slower). `large-v3` ~3GB not recommended on i5-7200U.
- Concurrency 1 per queue.

## Volumes

Edit `docker-compose.yml` env: `HOST_DOWNLOADS_DIR`, `HOST_DATA_DIR`, `HOST_MODELS_DIR` to map to ZimaOS shares.

