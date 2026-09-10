"""Application configuration."""

from functools import lru_cache
from typing import List

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

    model_config = SettingsConfigDict(
        env_prefix="QTUBE_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
