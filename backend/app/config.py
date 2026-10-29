"""Application settings loaded from environment variables (and a local, git-ignored .env).

The OpenAI key is held as a ``SecretStr`` so it is never rendered by ``repr``/logging.
"""

from __future__ import annotations

import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_ENV_FILES = (_BACKEND_DIR.parent / ".env", _BACKEND_DIR / ".env")


class LLMMode(StrEnum):
    LIVE = "live"
    OFFLINE = "offline"


def _env_files() -> tuple[Path, ...] | None:
    # Tests set SPECCHECK_DISABLE_DOTENV so a developer's real key is never picked up.
    return None if os.environ.get("SPECCHECK_DISABLE_DOTENV") else _ENV_FILES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(default=60.0, alias="OPENAI_TIMEOUT_SECONDS")
    use_embeddings: bool = Field(default=False, alias="SPECCHECK_USE_EMBEDDINGS")
    force_offline: bool = Field(default=False, alias="SPECCHECK_FORCE_OFFLINE")
    cors_origins: list[str] | str = Field(
        default=["http://localhost:5173"], alias="SPECCHECK_CORS_ORIGINS"
    )

    max_upload_mb: int = Field(default=10, alias="SPECCHECK_MAX_UPLOAD_MB")
    max_pdf_pages: int = Field(default=80, alias="SPECCHECK_MAX_PDF_PAGES")
    datasheet_ttl_seconds: int = Field(default=1800, alias="SPECCHECK_DATASHEET_TTL")
    check_ttl_seconds: int = Field(default=7200, alias="SPECCHECK_CHECK_TTL")

    agent_max_steps: int = Field(default=40, alias="SPECCHECK_AGENT_MAX_STEPS")
    agent_max_tokens: int = Field(default=150_000, alias="SPECCHECK_AGENT_MAX_TOKENS")
    agent_timeout_seconds: float = Field(default=240.0, alias="SPECCHECK_AGENT_TIMEOUT")
    agent_max_pages_read: int = Field(default=40, alias="SPECCHECK_AGENT_MAX_PAGES")
    min_confidence: float = Field(default=0.6, ge=0, le=1, alias="SPECCHECK_MIN_CONFIDENCE")
    demo_delay_seconds: float = Field(default=0.25, alias="SPECCHECK_DEMO_DELAY")

    rate_limit_checks: str = Field(default="10/minute", alias="SPECCHECK_RATE_LIMIT_CHECKS")
    rate_limit_uploads: str = Field(default="20/minute", alias="SPECCHECK_RATE_LIMIT_UPLOADS")
    max_concurrent_runs: int = Field(default=4, alias="SPECCHECK_MAX_CONCURRENT_RUNS")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and (not value.strip() or value.strip() == "sk-your-key-here"):
            return None
        return value

    @property
    def llm_mode(self) -> LLMMode:
        if self.openai_api_key is None or self.force_offline:
            return LLMMode.OFFLINE
        return LLMMode.LIVE

    @property
    def secret_values(self) -> list[str]:
        """Secrets that must never appear in logs or responses."""
        return [self.openai_api_key.get_secret_value()] if self.openai_api_key else []


def load_settings(**overrides: object) -> Settings:
    """Build settings, reading .env files unless disabled (tests)."""
    return Settings(_env_file=_env_files(), **overrides)  # type: ignore[call-arg]


@lru_cache
def get_settings() -> Settings:
    return load_settings()
