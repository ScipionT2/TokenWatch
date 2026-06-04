"""Production-readiness checks for Token-Tracker deployments."""

from __future__ import annotations

from typing import Any

from config import settings


VALID_BUDGET_MODES = {"observe", "warn", "block", "downgrade"}
PLACEHOLDER_ADMIN_KEYS = {
    "change-this-long-random-secret",
    "your-admin-key",
    "admin",
    "password",
    "tokenwatch-admin-key",
}
PLACEHOLDER_OPENAI_PREFIXES = ("sk-your", "your-", "change-me", "changeme")


def _check(name: str, level: str, message: str, fix: str) -> dict[str, str]:
    return {"name": name, "level": level, "message": message, "fix": fix}


def _admin_key_level(admin_key: str) -> str:
    normalized = admin_key.strip().lower()
    if not normalized:
        return "fail"
    if normalized in PLACEHOLDER_ADMIN_KEYS or len(admin_key) < 24:
        return "fail"
    return "pass"


def run_preflight() -> dict[str, Any]:
    """Return deployment checks with pass/warn/fail levels.

    These checks intentionally avoid network access. They validate the local env
    and container/deploy posture before a public demo or production instance is
    exposed.
    """
    checks: list[dict[str, str]] = []

    admin_level = _admin_key_level(settings.tokenwatch_admin_key)
    checks.append(_check(
        "admin_key",
        admin_level,
        "TOKENWATCH_ADMIN_KEY is configured" if admin_level == "pass" else "TOKENWATCH_ADMIN_KEY is missing or weak",
        "Set TOKENWATCH_ADMIN_KEY to a long random secret before exposing Token-Tracker.",
    ))

    openai_key = settings.openai_api_key.strip()
    openai_placeholder = openai_key.lower().startswith(PLACEHOLDER_OPENAI_PREFIXES)
    checks.append(_check(
        "openai_api_key",
        "pass" if openai_key and not openai_placeholder else "warn",
        "OPENAI_API_KEY is configured" if openai_key and not openai_placeholder else "OPENAI_API_KEY is not ready; proxy forwarding will be unavailable",
        "Set OPENAI_API_KEY for real proxy traffic, or keep demo mode read-only.",
    ))

    checks.append(_check(
        "demo_mode",
        "warn" if settings.tokenwatch_demo_mode else "pass",
        "TOKENWATCH_DEMO_MODE=true exposes public read-only HTML pages" if settings.tokenwatch_demo_mode else "TOKENWATCH_DEMO_MODE=false for private/admin-gated HTML pages",
        "Use true for portfolio demos; use false for private production dashboards.",
    ))

    budget_mode = settings.budget_mode.strip().lower()
    checks.append(_check(
        "budget_mode",
        "pass" if budget_mode in VALID_BUDGET_MODES else "fail",
        f"BUDGET_MODE={settings.budget_mode}",
        f"Set BUDGET_MODE to one of: {', '.join(sorted(VALID_BUDGET_MODES))}.",
    ))

    database_url = settings.database_url.strip()
    default_sqlite = database_url in {
        "sqlite+aiosqlite:///./tokenwatch.db",
        "sqlite:///./tokenwatch.db",
    }
    checks.append(_check(
        "database",
        "warn" if default_sqlite else "pass",
        f"DATABASE_URL={database_url}",
        "Use a Docker volume path like sqlite+aiosqlite:////app/data/tokenwatch.db or Postgres for durable production storage.",
    ))

    cors_origins = settings.cors_origins()
    wildcard_cors = cors_origins == ["*"]
    checks.append(_check(
        "cors",
        "warn" if wildcard_cors else "pass",
        "CORS allows every origin" if wildcard_cors else f"CORS restricted to {', '.join(cors_origins)}",
        "Set CORS_ALLOWED_ORIGINS=https://your-domain.com,https://api.your-domain.com for production.",
    ))

    levels = [check["level"] for check in checks]
    if "fail" in levels:
        status = "fail"
    elif "warn" in levels:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "summary": {
            "pass": levels.count("pass"),
            "warn": levels.count("warn"),
            "fail": levels.count("fail"),
        },
        "checks": checks,
    }
