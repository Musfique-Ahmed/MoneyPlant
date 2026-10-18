"""Application configuration loaded from environment variables.

Centralised so that the rest of the codebase does not import ``os.environ``
directly. Sensitive values are never logged or returned through public
endpoints. The :class:`Settings` instance is cached via ``lru_cache`` so
``get_settings()`` is cheap.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-wide configuration.

    Reads from ``backend/.env`` (relative to the current working directory
    when the backend is launched) and from process environment. No secret is
    ever exposed by ``/api/config/public`` — that endpoint exposes only safe
    boolean flags.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "sqlite:///./moneyplant.db"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # Server
    secret_key: str = Field(default="dev-only-change-me", min_length=8)
    log_level: str = "INFO"
    log_redact_financial: bool = True

    # AI defaults
    ai_default_mode: Literal["local", "openai", "anthropic"] = "local"
    ai_local_base_url: str = "http://localhost:11434/v1"
    ai_local_model: str = "llama3.1:8b"
    ai_timeout_seconds: int = 30

    # Provider API keys (optional)
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    # Laya (optional)
    laya_model: str | None = None
    laya_device: Literal["cpu", "cuda", "mps", "xpu"] = "cpu"

    # Uploads
    upload_max_bytes: int = 10 * 1024 * 1024  # 10 MB
    upload_allowed_extensions: tuple[str, ...] = (".csv", ".xlsx", ".xls")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key and self.anthropic_api_key.strip())

    @property
    def has_laya(self) -> bool:
        return bool(self.laya_model and self.laya_model.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
