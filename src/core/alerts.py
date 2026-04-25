"""Cost alerting system — catch runaway spend before it hurts.

Three alert levels:
- INFO: daily spend approaching budget
- WARNING: single request exceeds threshold
- CRITICAL: daily budget exceeded
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

from config import settings
from src.models.schemas import CostAlert, AlertLevel

logger = logging.getLogger(__name__)

# In-memory alert log (swap for persistent store in production)
_alert_history: list[CostAlert] = []
_daily_spend: float = 0.0
_last_reset_date: Optional[str] = None


def check_and_alert(
    request_cost: float,
    daily_total: float,
    model: str = "",
) -> Optional[CostAlert]:
    """Evaluate a request against budget thresholds.
    
    Called after every API request. Returns an alert if triggered, None otherwise.
    """
    global _daily_spend, _last_reset_date

    today = datetime.now().strftime("%Y-%m-%d")
    if _last_reset_date != today:
        _daily_spend = 0.0
        _last_reset_date = today

    _daily_spend += request_cost
    alert = None

    # CRITICAL: Daily budget exceeded
    if _daily_spend > settings.alert_daily_budget:
        alert = CostAlert(
            level=AlertLevel.CRITICAL,
            message=f"🚨 DAILY BUDGET EXCEEDED: ${_daily_spend:.2f} / ${settings.alert_daily_budget:.2f}. "
                    f"Model: {model}. Recommend pausing non-essential requests.",
            current_spend=_daily_spend,
            threshold=settings.alert_daily_budget,
            triggered_at=datetime.now(),
        )

    # WARNING: Single expensive request
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

    # INFO: Approaching budget (>80%)
    elif _daily_spend > settings.alert_daily_budget * 0.8:
        alert = CostAlert(
            level=AlertLevel.INFO,
            message=f"ℹ️ Daily spend at {(_daily_spend / settings.alert_daily_budget * 100):.0f}% "
                    f"of budget (${_daily_spend:.2f} / ${settings.alert_daily_budget:.2f}).",
            current_spend=_daily_spend,
            threshold=settings.alert_daily_budget,
            triggered_at=datetime.now(),
        )

    if alert:
        _alert_history.append(alert)
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
    if not settings.alert_webhook_url:
        return

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                settings.alert_webhook_url,
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
    # In production, use a background task queue
    pass


def get_alert_history(limit: int = 50) -> list[CostAlert]:
    """Recent alerts for the dashboard."""
    return list(reversed(_alert_history[-limit:]))


def get_daily_spend() -> float:
    """Current day's total spend."""
    return _daily_spend


def reset_daily_spend() -> None:
    """Manual reset for testing."""
    global _daily_spend
    _daily_spend = 0.0
