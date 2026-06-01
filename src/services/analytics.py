"""Analytics engine — turn logged requests into actionable spend insights."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from src.core.alerts import get_daily_spend
from src.models.schemas import UsageSummary, CostForecast
from src.services.request_logger import request_logger, RequestEntry


def log_request(entry: dict) -> None:
    """Record a completed API request through the canonical request logger."""
    timestamp = entry.get("logged_at") or entry.get("timestamp") or datetime.now()
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)

    prompt_tokens = int(entry.get("prompt_tokens", 0))
    completion_tokens = int(entry.get("completion_tokens", 0))
    total_tokens = int(entry.get("total_tokens", prompt_tokens + completion_tokens))

    request_logger.log(RequestEntry(
        model=entry.get("model", "unknown"),
        endpoint=entry.get("endpoint", ""),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=float(entry.get("cost_usd", 0.0)),
        latency_ms=float(entry.get("latency_ms", 0.0)),
        status_code=int(entry.get("status_code", 200)),
        cache_hit=bool(entry.get("cache_hit", False)),
        tokens_saved=int(entry.get("tokens_saved", 0)),
        cost_saved_usd=float(entry.get("cost_saved_usd", 0.0)),
        prompt_hash=entry.get("prompt_hash"),
        user_id=entry.get("user_id"),
        timestamp=timestamp,
        request_id=entry.get("request_id", ""),
        metadata=entry.get("metadata", {}),
    ))


def get_usage_summary(
    hours: int = 24,
    model_filter: Optional[str] = None,
) -> UsageSummary:
    """Aggregate usage stats for the given time window."""
    cutoff = datetime.now() - timedelta(hours=hours)
    filtered = [
        r for r in request_logger.entries()
        if r.timestamp >= cutoff
        and (model_filter is None or r.model == model_filter)
    ]

    if not filtered:
        return UsageSummary(
            period_start=cutoff,
            period_end=datetime.now(),
            total_requests=0,
            total_tokens=0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_cost_usd=0.0,
            total_saved_usd=0.0,
            avg_latency_ms=0.0,
            cache_hit_rate=0.0,
            requests_by_model={},
            cost_by_model={},
            top_expensive_requests=[],
            duplicate_request_count=0,
        )

    total_tokens = sum(r.total_tokens for r in filtered)
    total_prompt = sum(r.prompt_tokens for r in filtered)
    total_completion = sum(r.completion_tokens for r in filtered)
    total_cost = sum(r.cost_usd for r in filtered)
    total_saved = sum(r.cost_saved_usd for r in filtered)
    cache_hits = sum(1 for r in filtered if r.cache_hit)
    latencies = [r.latency_ms for r in filtered if r.latency_ms > 0]

    by_model_count: dict[str, int] = defaultdict(int)
    by_model_cost: dict[str, float] = defaultdict(float)
    for r in filtered:
        by_model_count[r.model] += 1
        by_model_cost[r.model] += r.cost_usd

    sorted_by_cost = sorted(filtered, key=lambda r: r.cost_usd, reverse=True)
    top_expensive = [
        {
            "model": r.model,
            "cost_usd": round(r.cost_usd, 4),
            "total_tokens": r.total_tokens,
            "timestamp": r.timestamp.isoformat(),
            "request_id": r.request_id,
            "endpoint": r.endpoint,
        }
        for r in sorted_by_cost[:10]
    ]

    hashes = [r.prompt_hash for r in filtered if r.prompt_hash]
    seen = set()
    dupes = 0
    for h in hashes:
        if h in seen:
            dupes += 1
        seen.add(h)

    return UsageSummary(
        period_start=cutoff,
        period_end=datetime.now(),
        total_requests=len(filtered),
        total_tokens=total_tokens,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_cost_usd=round(total_cost, 4),
        total_saved_usd=round(total_saved, 4),
        avg_latency_ms=round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        cache_hit_rate=round(cache_hits / len(filtered) * 100, 1) if filtered else 0.0,
        requests_by_model=dict(by_model_count),
        cost_by_model={k: round(v, 4) for k, v in by_model_cost.items()},
        top_expensive_requests=top_expensive,
        duplicate_request_count=dupes,
    )


def get_cost_forecast() -> CostForecast:
    """Project future spend based on current usage patterns."""
    daily_spend = get_daily_spend()
    from config import settings

    budget = settings.alert_daily_budget
    monthly = daily_spend * 30
    yearly = daily_spend * 365
    utilization = (daily_spend / budget * 100) if budget > 0 else 0

    if daily_spend > budget:
        days_left = 0
        rec = f"🚨 OVER BUDGET — spending ${daily_spend:.2f}/day against ${budget:.2f} limit. Reduce usage or increase budget."
    elif daily_spend > budget * 0.8:
        days_left = None
        rec = f"⚠️ At {utilization:.0f}% of daily budget. Consider optimizing prompts or switching to cheaper models."
    elif daily_spend > 0:
        days_left = None
        rec = f"✅ Healthy — ${daily_spend:.2f}/day, projecting ${monthly:.2f}/month. Budget utilization: {utilization:.0f}%."
    else:
        days_left = None
        rec = "No spend recorded today."

    return CostForecast(
        current_daily_spend=round(daily_spend, 4),
        projected_monthly_spend=round(monthly, 2),
        projected_yearly_spend=round(yearly, 2),
        budget_daily=budget,
        budget_utilization_pct=round(utilization, 1),
        days_until_budget_exceeded=days_left,
        recommendation=rec,
    )
