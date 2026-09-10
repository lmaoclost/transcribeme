"""Whisper transcription using faster-whisper."""

from __future__ import annotations

import time
from pathlib import Path

from faster_whisper import WhisperModel

from app.config import get_settings

settings = get_settings()


class WhisperTranscriber:
    """faster-whisper transcriber."""

    def __init__(self, model: str | None = None) -> None:
        model_name = model or settings.whisper_model
        self.device = settings.transcription_device
        self.compute_type = settings.transcription_compute_type

        print(f"Loading faster-whisper model '{model_name}' on {self.device}")
        self.model = WhisperModel(
            model_name,
            device=self.device,
            compute_type=self.compute_type,
        )
        print(f"Model loaded successfully on {self.device}")

    def transcribe_audio(self, audio_file: Path) -> tuple[str, str | None]:
        """Transcribe audio, auto-detect language. Returns (text, lang)."""
        start_time = time.time()
        segments, info = self.model.transcribe(str(audio_file), language=None)
        lang = getattr(info, "language", None) if info else None
        prob = getattr(info, "language_probability", None) if info else None
        transcription_text = "".join(segment.text for segment in segments).strip()
        elapsed_time = time.time() - start_time
        print(f"Transcription completed in {elapsed_time:.2f}s lang={lang} prob={prob}")
        return transcription_text, lang

    @staticmethod
    def needs_splitting(audio_file: Path, threshold_minutes: int = 30) -> bool:
        """Check if file exceeds threshold via ffprobe/ffmpeg."""
        try:
            import subprocess
            import json

            # try ffprobe duration
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(audio_file)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                duration = float(data.get("format", {}).get("duration", 0))
                return duration > threshold_minutes * 60
        except Exception:
            pass
        # fallback by file size > 500MB ~ assume long
        try:
            return audio_file.stat().st_size > 500 * 1024 * 1024
        except Exception:
            return False
