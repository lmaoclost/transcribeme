"""Application configuration."""

import json
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    env: str = "development"
    redis_url: str = "redis://redis:6379/0"
    database_url: str = "sqlite:///./data/qtube.db"
    downloads_dir: str = "downloads"
    models_dir: str = "models"
    whisper_model: str = "small"
    transcription_device: str = "cpu"
    transcription_compute_type: str = "int8"
    ytdlp_cookies_file: str | None = None
    cors_origins: List[str] = ["*"]
    # transcribeme additions
    max_upload_size_mb: int = 2048
    upload_chunk_size_mb: int = 5
    cleanup_days: int = 7
    transcription_target_lang: str = "pt"
    splitter_threshold_minutes: int = 30
    splitter_chunk_minutes: int = 20
    # NLLB translation
    translation_model: str = "facebook/nllb-200-distilled-600M"
    translation_device: str = "cpu"
    translation_target_lang_code: str = "por_Latn"
    transcription_speed: float = 1.5
    youtube_prefer_captions: bool = True
    youtube_sub_langs: str = "pt,pt-BR,pt-PT,en,es,fr,de,ja"

    model_config = SettingsConfigDict(
        env_prefix="QTUBE_",
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
    )

    @field_validator(
        "max_upload_size_mb",
        "upload_chunk_size_mb",
        "cleanup_days",
        "splitter_threshold_minutes",
        "splitter_chunk_minutes",
        "transcription_speed",
        "whisper_model",
        "transcription_device",
        "transcription_compute_type",
        "transcription_target_lang",
        "translation_model",
        "translation_device",
        "translation_target_lang_code",
        "youtube_sub_langs",
        "redis_url",
        "database_url",
        "downloads_dir",
        "models_dir",
        mode="before",
    )
    @classmethod
    def _empty_to_default(cls, v, info):
        # ZimaOS/CasaOS injects "" for blank UI fields — fall back to defaults
        if v == "":
            return cls.model_fields[info.field_name].default
        return v


SETTINGS_FILE = Path("data/settings.json")

def get_settings() -> Settings:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text())
            return Settings(**data)
        except Exception:
            pass
    return Settings()

def save_settings(updates: dict) -> Settings:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if SETTINGS_FILE.exists():
        try:
            current = json.loads(SETTINGS_FILE.read_text())
        except Exception:
            current = {}
    current.update({k: v for k, v in updates.items() if v is not None and v != ""})
    SETTINGS_FILE.write_text(json.dumps(current, indent=2))
    return get_settings()
