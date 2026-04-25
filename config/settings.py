"""Centralized config — every secret lives in env vars, never in code."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    # Database
    database_url: str = "sqlite+aiosqlite:///./sentinel.db"

    # Cost alerts
    alert_daily_budget: float = 50.00
    alert_per_request_max: float = 5.00
    alert_webhook_url: Optional[str] = None

    # Token optimization
    max_prompt_tokens: int = 8000
    enable_prompt_compression: bool = True
    enable_cache_dedup: bool = True
    cache_ttl_seconds: int = 3600

    # Rate limiting
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
