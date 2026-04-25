"""Analytics engine — turn raw request logs into actionable insights.

The goal: answer "where is my money going?" in under a second.
"""

from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

from src.core.pricing import calculate_cost, suggest_cheaper_model, estimate_batch_cost
from src.core.alerts import get_daily_spend
from src.models.schemas import UsageSummary, CostForecast


# In-memory request store (swap for DB in production)
_request_log: list[dict] = []


def log_request(entry: dict) -> None:
    """Record a completed API request."""
    _request_log.append({**entry, "logged_at": datetime.now()})


def get_usage_summary(
    hours: int = 24,
    model_filter: Optional[str] = None,
) -> UsageSummary:
    """Aggregate usage stats for the given time window."""
    cutoff = datetime.now() - timedelta(hours=hours)
    filtered = [
        r for r in _request_log
        if r.get("logged_at", datetime.min) >= cutoff
        and (model_filter is None or r.get("model") == model_filter)
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

    total_tokens = sum(r.get("total_tokens", 0) for r in filtered)
    total_prompt = sum(r.get("prompt_tokens", 0) for r in filtered)
    total_completion = sum(r.get("completion_tokens", 0) for r in filtered)
    total_cost = sum(r.get("cost_usd", 0) for r in filtered)
    total_saved = sum(r.get("cost_saved_usd", 0) for r in filtered)
    cache_hits = sum(1 for r in filtered if r.get("cache_hit", False))
    latencies = [r.get("latency_ms", 0) for r in filtered if r.get("latency_ms", 0) > 0]

    # Group by model
    by_model_count: dict[str, int] = defaultdict(int)
    by_model_cost: dict[str, float] = defaultdict(float)
    for r in filtered:
        model = r.get("model", "unknown")
        by_model_count[model] += 1
        by_model_cost[model] += r.get("cost_usd", 0)

    # Find most expensive requests
    sorted_by_cost = sorted(filtered, key=lambda r: r.get("cost_usd", 0), reverse=True)
    top_expensive = [
        {
            "model": r.get("model"),
            "cost_usd": round(r.get("cost_usd", 0), 4),
            "total_tokens": r.get("total_tokens", 0),
            "timestamp": r.get("logged_at", "").isoformat() if isinstance(r.get("logged_at"), datetime) else str(r.get("logged_at", "")),
        }
        for r in sorted_by_cost[:10]
    ]

    # Count duplicate prompts
    hashes = [r.get("prompt_hash") for r in filtered if r.get("prompt_hash")]
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
