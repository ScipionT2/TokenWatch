"""Centralized config — every secret lives in env vars, never in code."""

from pydantic_settings import BaseSettings
from typing import Optional


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings(BaseSettings):
    # OpenAI
    openai_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    tokenwatch_admin_key: str = ""  # optional: protects control-plane admin endpoints
    tokenwatch_demo_mode: bool = False  # public read-only HTML pages; admin APIs stay protected
    tokenwatch_seed_demo: bool = False  # seed demo dashboard data on startup when storage is empty
    cors_allowed_origins: str = "*"  # comma-separated origins; use explicit domains in production

    # Database
    database_url: str = "sqlite+aiosqlite:///./tokenwatch.db"

    # Cost alerts / budget controls
    alert_daily_budget: float = 50.00
    alert_per_request_max: float = 5.00
    alert_webhook_url: Optional[str] = None
    budget_mode: str = "observe"  # observe | warn | block | downgrade

    # Token optimization
    max_prompt_tokens: int = 8000
    enable_prompt_compression: bool = True
    enable_cache_dedup: bool = True
    cache_ttl_seconds: int = 3600

    # Rate limiting
    rate_limit_rpm: int = 60
    rate_limit_tpm: int = 100000

    def cors_origins(self) -> list[str]:
        """Return normalized CORS origins from the comma-separated env var."""
        origins = _split_csv(self.cors_allowed_origins)
        return origins or ["*"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
