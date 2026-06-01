"""Cost alerting system — catch runaway spend before it hurts.

Alerts and webhook config are persisted in SQLite so restarts do not erase the
current alert configuration or recent alert history.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from config import settings
from src.models.schemas import CostAlert, AlertLevel

logger = logging.getLogger(__name__)

_alert_history: list[CostAlert] = []
_daily_spend: float = 0.0
_last_reset_date: Optional[str] = None
_webhook_config: Optional[dict] = None


def _database_path(database_url: str) -> Path:
    if database_url.startswith("sqlite+aiosqlite:///"):
        raw = database_url.removeprefix("sqlite+aiosqlite:///")
    elif database_url.startswith("sqlite:///"):
        raw = database_url.removeprefix("sqlite:///")
    else:
        parsed = urlparse(database_url)
        raw = parsed.path.lstrip("/") if parsed.scheme.startswith("sqlite") else "tokenwatch.db"
    path = Path(raw)
    if not path.is_absolute():
        path = Path.cwd() / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


_DB_PATH = _database_path(settings.database_url)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_tables() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                current_spend REAL NOT NULL,
                threshold REAL NOT NULL,
                triggered_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                url TEXT NOT NULL,
                threshold REAL,
                enabled INTEGER NOT NULL
            )
            """
        )
        conn.commit()


def _load_state() -> None:
    global _alert_history, _webhook_config
    _ensure_tables()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 200").fetchall()
        _alert_history = [
            CostAlert(
                level=AlertLevel(row["level"]),
                message=row["message"],
                current_spend=row["current_spend"],
                threshold=row["threshold"],
                triggered_at=datetime.fromisoformat(row["triggered_at"]),
            )
            for row in reversed(rows)
        ]
        cfg = conn.execute("SELECT * FROM webhook_config WHERE id = 1").fetchone()
        if cfg:
            _webhook_config = {
                "url": cfg["url"],
                "threshold": cfg["threshold"],
                "enabled": bool(cfg["enabled"]),
            }


def _persist_alert(alert: CostAlert) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO alerts (level, message, current_spend, threshold, triggered_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (alert.level.value, alert.message, alert.current_spend, alert.threshold, alert.triggered_at.isoformat()),
        )
        conn.commit()


def check_and_alert(
    request_cost: float,
    daily_total: float,
    model: str = "",
) -> Optional[CostAlert]:
    """Evaluate a request against budget thresholds."""
    global _daily_spend, _last_reset_date

    today = datetime.now().strftime("%Y-%m-%d")
    if _last_reset_date != today:
        _daily_spend = 0.0
        _last_reset_date = today

    _daily_spend += request_cost
    alert = None

    if _daily_spend > settings.alert_daily_budget:
        alert = CostAlert(
            level=AlertLevel.CRITICAL,
            message=f"🚨 DAILY BUDGET EXCEEDED: ${_daily_spend:.2f} / ${settings.alert_daily_budget:.2f}. "
                    f"Model: {model}. Recommend pausing non-essential requests.",
            current_spend=_daily_spend,
            threshold=settings.alert_daily_budget,
            triggered_at=datetime.now(),
        )
    elif request_cost > settings.alert_per_request_max:
        alert = CostAlert(
            level=AlertLevel.WARNING,
            message=f"⚠️ Expensive request: ${request_cost:.4f} on {model}. "
                    f"Threshold: ${settings.alert_per_request_max:.2f}. "
                    f"Consider using a cheaper model for this task.",
            current_spend=_daily_spend,
            threshold=settings.alert_per_request_max,
            triggered_at=datetime.now(),
        )
    elif _daily_spend > settings.alert_daily_budget * 0.8:
        alert = CostAlert(
            level=AlertLevel.INFO,
            message=f"ℹ️ Daily spend at {(_daily_spend / settings.alert_daily_budget * 100):.0f}% "
                    f"of budget (${_daily_spend:.2f} / ${settings.alert_daily_budget:.2f}).",
            current_spend=_daily_spend,
            threshold=settings.alert_daily_budget,
            triggered_at=datetime.now(),
        )

    if not alert and _webhook_config and _webhook_config.get("threshold"):
        custom_threshold = _webhook_config["threshold"]
        if _daily_spend > custom_threshold:
            alert = CostAlert(
                level=AlertLevel.WARNING,
                message=f"⚠️ Custom threshold exceeded: ${_daily_spend:.2f} / ${custom_threshold:.2f}. Model: {model}.",
                current_spend=_daily_spend,
                threshold=custom_threshold,
                triggered_at=datetime.now(),
            )

    if alert:
        _alert_history.append(alert)
        _persist_alert(alert)
        logger.log(
            logging.CRITICAL if alert.level == AlertLevel.CRITICAL else
            logging.WARNING if alert.level == AlertLevel.WARNING else
            logging.INFO,
            alert.message,
        )
        _fire_webhook(alert)

    return alert


async def _fire_webhook_async(alert: CostAlert) -> None:
    """Send alert to configured webhook (Slack, Discord, etc.)."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url,
                json={
                    "level": alert.level.value,
                    "message": alert.message,
                    "spend": alert.current_spend,
                    "threshold": alert.threshold,
                    "timestamp": alert.triggered_at.isoformat(),
                },
                timeout=5.0,
            )
    except Exception as e:
        logger.error(f"Failed to fire alert webhook: {e}")


def _fire_webhook(alert: CostAlert) -> None:
    """Sync wrapper — webhooks are best-effort, don't block the request."""
    webhook_url = _get_webhook_url()
    if not webhook_url:
        return
    try:
        with httpx.Client() as client:
            client.post(
                webhook_url,
                json={
                    "level": alert.level.value,
                    "message": alert.message,
                    "spend": alert.current_spend,
                    "threshold": alert.threshold,
                    "timestamp": alert.triggered_at.isoformat(),
                },
                timeout=5.0,
            )
    except Exception as e:
        logger.error(f"Failed to fire alert webhook: {e}")


def _get_webhook_url() -> Optional[str]:
    if _webhook_config and _webhook_config.get("enabled"):
        return _webhook_config.get("url")
    return settings.alert_webhook_url


def configure_webhook(url: str, threshold: Optional[float] = None, enabled: bool = True) -> dict:
    """Configure webhook delivery at runtime and persist it."""
    global _webhook_config
    _webhook_config = {
        "url": url,
        "threshold": threshold,
        "enabled": enabled,
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO webhook_config (id, url, threshold, enabled)
            VALUES (1, ?, ?, ?)
            """,
            (url, threshold, int(enabled)),
        )
        conn.commit()
    logger.info(f"Webhook configured: {url} (threshold: {threshold}, enabled: {enabled})")
    return _webhook_config


def get_webhook_config() -> Optional[dict]:
    return _webhook_config


def get_alert_history(limit: int = 50) -> list[CostAlert]:
    return list(reversed(_alert_history[-limit:]))


def get_daily_spend() -> float:
    return _daily_spend


def reset_daily_spend() -> None:
    global _daily_spend
    _daily_spend = 0.0


def reset_alert_state(clear_persistent: bool = False) -> None:
    """Reset alert/webhook state for tests or local maintenance."""
    global _daily_spend, _alert_history, _webhook_config
    _daily_spend = 0.0
    _alert_history = []
    _webhook_config = None
    if clear_persistent:
        with _connect() as conn:
            conn.execute("DELETE FROM alerts")
            conn.execute("DELETE FROM webhook_config")
            conn.commit()


_load_state()
