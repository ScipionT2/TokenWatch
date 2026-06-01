"""Budget enforcement controls for TokenWatch proxy requests.

Runtime budget config is persisted in SQLite so enforcement mode survives
restarts while keeping local setup zero-config.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config import settings
from src.core.alerts import get_daily_spend
from src.core.pricing import suggest_cheaper_model


class BudgetMode(str, Enum):
    OBSERVE = "observe"
    WARN = "warn"
    BLOCK = "block"
    DOWNGRADE = "downgrade"


@dataclass
class BudgetConfig:
    mode: BudgetMode = BudgetMode.OBSERVE
    daily_budget: float = settings.alert_daily_budget
    per_request_max: float = settings.alert_per_request_max
    downgrade_task_type: str = "general"


@dataclass
class BudgetDecision:
    allowed: bool
    mode: str
    action: str
    model: str
    original_model: str
    estimated_cost_usd: float
    reason: str
    warning: Optional[str] = None


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


def _ensure_table() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budget_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                mode TEXT NOT NULL,
                daily_budget REAL NOT NULL,
                per_request_max REAL NOT NULL,
                downgrade_task_type TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _default_config() -> BudgetConfig:
    return BudgetConfig(
        mode=BudgetMode(getattr(settings, "budget_mode", "observe")),
        daily_budget=settings.alert_daily_budget,
        per_request_max=settings.alert_per_request_max,
        downgrade_task_type="general",
    )


def _load_config() -> BudgetConfig:
    _ensure_table()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM budget_config WHERE id = 1").fetchone()
    if not row:
        return _default_config()
    return BudgetConfig(
        mode=BudgetMode(row["mode"]),
        daily_budget=row["daily_budget"],
        per_request_max=row["per_request_max"],
        downgrade_task_type=row["downgrade_task_type"],
    )


def _persist_config(config: BudgetConfig) -> None:
    _ensure_table()
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO budget_config
            (id, mode, daily_budget, per_request_max, downgrade_task_type)
            VALUES (1, ?, ?, ?, ?)
            """,
            (config.mode.value, config.daily_budget, config.per_request_max, config.downgrade_task_type),
        )
        conn.commit()


_budget_config = _load_config()


def configure_budget(
    mode: str,
    daily_budget: Optional[float] = None,
    per_request_max: Optional[float] = None,
    downgrade_task_type: Optional[str] = None,
) -> dict:
    """Configure and persist runtime budget enforcement."""
    global _budget_config
    parsed_mode = BudgetMode(mode)
    _budget_config = BudgetConfig(
        mode=parsed_mode,
        daily_budget=_budget_config.daily_budget if daily_budget is None else daily_budget,
        per_request_max=_budget_config.per_request_max if per_request_max is None else per_request_max,
        downgrade_task_type=downgrade_task_type or _budget_config.downgrade_task_type,
    )
    _persist_config(_budget_config)
    return get_budget_config()


def get_budget_config() -> dict:
    return {
        "mode": _budget_config.mode.value,
        "daily_budget": _budget_config.daily_budget,
        "per_request_max": _budget_config.per_request_max,
        "downgrade_task_type": _budget_config.downgrade_task_type,
    }


def evaluate_budget(model: str, estimated_cost_usd: float) -> BudgetDecision:
    """Decide whether a request should proceed, warn, block, or downgrade."""
    daily_spend = get_daily_spend()
    projected_daily = daily_spend + estimated_cost_usd
    over_daily = projected_daily > _budget_config.daily_budget
    over_request = estimated_cost_usd > _budget_config.per_request_max
    reason = "within budget"

    if over_daily:
        reason = f"projected daily spend ${projected_daily:.4f} exceeds ${_budget_config.daily_budget:.4f} budget"
    elif over_request:
        reason = f"estimated request cost ${estimated_cost_usd:.4f} exceeds ${_budget_config.per_request_max:.4f} limit"

    if _budget_config.mode == BudgetMode.BLOCK and (over_daily or over_request):
        return BudgetDecision(
            allowed=False,
            mode=_budget_config.mode.value,
            action="block",
            model=model,
            original_model=model,
            estimated_cost_usd=estimated_cost_usd,
            reason=reason,
            warning=reason,
        )

    if _budget_config.mode == BudgetMode.DOWNGRADE and (over_daily or over_request):
        cheaper, savings_pct = suggest_cheaper_model(model, _budget_config.downgrade_task_type)
        if cheaper != model:
            return BudgetDecision(
                allowed=True,
                mode=_budget_config.mode.value,
                action="downgrade",
                model=cheaper,
                original_model=model,
                estimated_cost_usd=estimated_cost_usd,
                reason=f"{reason}; downgraded to {cheaper} for ~{savings_pct}% savings",
                warning=reason,
            )

    action = "warn" if _budget_config.mode == BudgetMode.WARN and (over_daily or over_request) else "observe"
    return BudgetDecision(
        allowed=True,
        mode=_budget_config.mode.value,
        action=action,
        model=model,
        original_model=model,
        estimated_cost_usd=estimated_cost_usd,
        reason=reason,
        warning=reason if action == "warn" else None,
    )
