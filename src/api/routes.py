"""API routes — the control plane for monitoring and optimizing OpenAI spend."""

import csv
import io
import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.models.schemas import (
    HealthResponse,
    ProxyRequest,
    ProxyResponse,
    PromptAnalysis,
    UsageSummary,
    CostForecast,
    WebhookConfig,
)
from src.core.pricing import calculate_cost, get_tier, suggest_cheaper_model, estimate_batch_cost
from src.core.token_counter import count_message_tokens, hash_prompt
from src.core.prompt_optimizer import analyze_prompt, compress_messages
from src.core.cache import response_cache
from src.core.alerts import check_and_alert, get_alert_history, get_daily_spend, configure_webhook, get_webhook_config
from src.services.analytics import log_request, get_usage_summary, get_cost_forecast
from src.services.request_logger import request_logger, RequestEntry
from src.middleware.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Health ---

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """System health with cache and request stats."""
    cache_stats = response_cache.stats()
    return HealthResponse(
        cache_entries=cache_stats["entries"],
        requests_logged_today=0,  # TODO: wire to analytics
    )


# --- Prompt Analysis ---

@router.post("/analyze/prompt", response_model=PromptAnalysis)
async def analyze_prompt_endpoint(request: ProxyRequest):
    """Analyze a prompt for waste, redundancy, and optimization opportunities.
    
    Send the same messages you'd send to OpenAI — get back a cost breakdown
    and actionable suggestions before spending a single token.
    """
    return analyze_prompt(request.messages, request.model)


@router.post("/optimize/prompt")
async def optimize_prompt(request: ProxyRequest):
    """Auto-compress a prompt and return the optimized version with savings."""
    original_tokens = count_message_tokens(request.messages, request.model)
    compressed = compress_messages(request.messages, request.model)
    optimized_tokens = count_message_tokens(compressed, request.model)

    original_cost = calculate_cost(request.model, original_tokens, 0)
    optimized_cost = calculate_cost(request.model, optimized_tokens, 0)

    return {
        "original_tokens": original_tokens,
        "optimized_tokens": optimized_tokens,
        "tokens_saved": original_tokens - optimized_tokens,
        "savings_pct": round((original_tokens - optimized_tokens) / original_tokens * 100, 1) if original_tokens else 0,
        "original_cost_estimate": original_cost,
        "optimized_cost_estimate": optimized_cost,
        "optimized_messages": compressed,
    }


# --- Cost Estimation ---

@router.post("/estimate/cost")
async def estimate_cost(request: ProxyRequest):
    """Pre-request cost estimate — know what you'll spend before you spend it."""
    prompt_tokens = count_message_tokens(request.messages, request.model)
    # Estimate completion tokens (conservative 1:1 ratio, capped at max_tokens)
    est_completion = min(prompt_tokens, request.max_tokens or 4000)
    cost = calculate_cost(request.model, prompt_tokens, est_completion)
    tier = get_tier(request.model)
    cheaper, savings_pct = suggest_cheaper_model(request.model)

    return {
        "model": request.model,
        "model_tier": tier.value,
        "prompt_tokens": prompt_tokens,
        "estimated_completion_tokens": est_completion,
        "estimated_cost_usd": cost,
        "cheaper_alternative": {
            "model": cheaper,
            "estimated_cost_usd": calculate_cost(cheaper, prompt_tokens, est_completion),
            "savings_pct": savings_pct,
        } if cheaper != request.model else None,
    }


@router.post("/estimate/batch")
async def estimate_batch(
    model: str,
    avg_prompt_tokens: int,
    avg_completion_tokens: int,
    count: int,
):
    """Estimate total cost for a batch of similar requests."""
    return estimate_batch_cost(model, avg_prompt_tokens, avg_completion_tokens, count)


# --- Analytics ---

@router.get("/analytics/usage", response_model=UsageSummary)
async def usage_summary(hours: int = 24, model: str = None):
    """Usage breakdown for the given time window."""
    return get_usage_summary(hours=hours, model_filter=model)


@router.get("/analytics/forecast", response_model=CostForecast)
async def cost_forecast():
    """Projected spend based on current usage patterns."""
    return get_cost_forecast()


@router.get("/analytics/alerts")
async def alerts(limit: int = 50):
    """Recent cost alerts."""
    return {"alerts": [a.model_dump() for a in get_alert_history(limit)]}


@router.post("/alerts/configure")
async def configure_alerts_webhook(config: WebhookConfig):
    """Configure webhook delivery for alerts.
    
    Set a URL to receive POST notifications when cost alerts fire.
    Optionally set a custom spend threshold.
    """
    result = configure_webhook(
        url=config.url,
        threshold=config.threshold,
        enabled=config.enabled,
    )
    return {"status": "configured", "webhook": result}


@router.get("/alerts/webhook")
async def get_alerts_webhook():
    """Get current webhook configuration."""
    config = get_webhook_config()
    if not config:
        return {"configured": False, "webhook": None}
    return {"configured": True, "webhook": config}


# --- Cache Management ---

@router.get("/cache/stats")
async def cache_stats():
    """Cache performance metrics."""
    return response_cache.stats()


@router.post("/cache/clear")
async def clear_cache():
    """Flush the response cache."""
    count = response_cache.clear()
    return {"cleared": count}


# --- Rate Limiter ---

@router.get("/rate-limit/status")
async def rate_limit_status():
    """Current rate limiter state."""
    return rate_limiter.stats()


@router.post("/rate-limit/check")
async def rate_limit_check(estimated_tokens: int = 1000):
    """Check if a request would be rate-limited."""
    return rate_limiter.check(estimated_tokens)


# --- Request Logging & History ---

@router.post("/log")
async def log_api_request(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    timestamp: Optional[str] = None,
    request_id: Optional[str] = None,
):
    """Log an API request for tracking and analysis.
    
    Record every API call with model, token counts, and cost.
    Use this to build a complete picture of your OpenAI spend.
    """
    ts = datetime.fromisoformat(timestamp) if timestamp else datetime.now()
    entry = RequestEntry(
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost_usd,
        timestamp=ts,
        request_id=request_id or str(uuid.uuid4())[:8],
    )
    request_logger.log(entry)
    return {
        "status": "logged",
        "request_id": entry.request_id,
        "total_logged": request_logger.count(),
    }


@router.get("/history")
async def request_history(
    limit: int = Query(50, ge=1, le=1000),
    model: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Retrieve recent API request history with optional filtering.
    
    Filter by model name, date range, or both. Returns newest first.
    """
    sd = datetime.fromisoformat(start_date) if start_date else None
    ed = datetime.fromisoformat(end_date) if end_date else None

    entries = request_logger.get_history(
        limit=limit,
        model=model,
        start_date=sd,
        end_date=ed,
    )
    return {
        "entries": entries,
        "count": len(entries),
        "total_logged": request_logger.count(),
        "total_cost_usd": request_logger.total_cost(),
    }


# --- Export ---

@router.get("/export/json")
async def export_json(
    model: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Export request history as JSON."""
    sd = datetime.fromisoformat(start_date) if start_date else None
    ed = datetime.fromisoformat(end_date) if end_date else None
    entries = request_logger.get_history(
        limit=10000,
        model=model,
        start_date=sd,
        end_date=ed,
    )
    return {"entries": entries, "count": len(entries)}


@router.get("/export/csv")
async def export_csv(
    model: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Export request history as CSV with proper Content-Disposition header."""
    sd = datetime.fromisoformat(start_date) if start_date else None
    ed = datetime.fromisoformat(end_date) if end_date else None
    entries = request_logger.get_history(
        limit=10000,
        model=model,
        start_date=sd,
        end_date=ed,
    )

    def generate_csv():
        output = io.StringIO()
        fieldnames = [
            "model", "prompt_tokens", "completion_tokens",
            "total_tokens", "cost_usd", "timestamp", "request_id",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        for entry in entries:
            writer.writerow(entry)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=api_sentinel_export.csv"},
    )


# --- Model Pricing ---

@router.get("/pricing/{model}")
async def model_pricing(model: str):
    """Look up pricing for any OpenAI model."""
    from src.core.pricing import get_pricing, MODEL_PRICING
    input_price, output_price, tier = get_pricing(model)
    return {
        "model": model,
        "tier": tier.value,
        "input_per_1m_tokens": input_price,
        "output_per_1m_tokens": output_price,
        "input_per_1k_tokens": round(input_price / 1000, 4),
        "output_per_1k_tokens": round(output_price / 1000, 4),
    }


@router.get("/pricing")
async def all_pricing():
    """Full pricing table for all known models."""
    from src.core.pricing import MODEL_PRICING
    return {
        model: {
            "input_per_1m": price[0],
            "output_per_1m": price[1],
            "tier": price[2].value,
        }
        for model, price in sorted(MODEL_PRICING.items())
    }
