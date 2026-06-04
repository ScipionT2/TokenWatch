"""API routes — Token-Tracker control plane and OpenAI-compatible proxy."""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import datetime
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from src.models.schemas import (
    HealthResponse,
    ProxyRequest,
    PromptAnalysis,
    UsageSummary,
    CostForecast,
    WebhookConfig,
    ModelRecommendationRequest,
    ModelRecommendationResponse,
    ProjectCreate,
    ProjectResponse,
    APIKeyCreate,
    APIKeyResponse,
)
from src.core.pricing import calculate_cost, get_tier, suggest_cheaper_model, estimate_batch_cost
from src.core.recommendations import recommend_model
from src.core.token_counter import count_message_tokens
from src.core.prompt_optimizer import analyze_prompt, compress_messages
from src.core.cache import response_cache
from src.core.alerts import check_and_alert, get_alert_history, get_daily_spend, configure_webhook, get_webhook_config
from src.core.budget import configure_budget, get_budget_config
from src.core.auth import require_admin_key, admin_auth_enabled, demo_mode_enabled, set_admin_session_cookie
from src.core.preflight import run_preflight
from src.middleware.rate_limiter import rate_limiter
from src.services.analytics import get_usage_summary, get_cost_forecast
from src.services.projects import project_store, project_to_dict
from src.services.proxy import proxy_to_openai
from src.services.request_logger import request_logger, RequestEntry

logger = logging.getLogger(__name__)
router = APIRouter()
proxy_router = APIRouter()


# --- Health ---

@router.get("/admin/verify")
async def verify_admin(response: Response, _: bool = Depends(require_admin_key)):
    """Verify an admin key for browser dashboard/setup unlocks."""
    if admin_auth_enabled():
        set_admin_session_cookie(response)
    return {"status": "ok", "admin": True}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """System health with cache and request stats."""
    cache_stats = response_cache.stats()
    return HealthResponse(
        cache_entries=cache_stats["entries"],
        requests_logged_today=request_logger.count_today(),
        admin_auth_enabled=admin_auth_enabled(),
        demo_mode=demo_mode_enabled(),
        preflight_status=run_preflight()["status"],
    )


@router.get("/preflight")
async def preflight(_: bool = Depends(require_admin_key)):
    """Production-readiness checks for deploys and public demos."""
    return run_preflight()


# --- Prompt Analysis ---

@router.post("/analyze/prompt", response_model=PromptAnalysis)
async def analyze_prompt_endpoint(request: ProxyRequest):
    """Analyze a prompt for waste, redundancy, and optimization opportunities."""
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


# --- Model Recommendations ---

@router.post("/recommend/model", response_model=ModelRecommendationResponse)
async def recommend_model_endpoint(request: ModelRecommendationRequest):
    """Task-aware recommendation for cheaper model routing."""
    return recommend_model(
        current_model=request.current_model,
        task_type=request.task_type,
        prompt_tokens=request.prompt_tokens,
        completion_tokens=request.completion_tokens,
        monthly_requests=request.monthly_requests,
    )


# --- Budget Controls ---

@router.get("/budget/config")
async def budget_config():
    """Current budget enforcement configuration."""
    return get_budget_config()


@router.post("/budget/config")
async def set_budget_config(
    mode: str = "observe",
    daily_budget: Optional[float] = None,
    per_request_max: Optional[float] = None,
    downgrade_task_type: Optional[str] = None,
    _: bool = Depends(require_admin_key),
):
    """Set hard budget control mode: observe, warn, block, or downgrade."""
    try:
        config = configure_budget(mode, daily_budget, per_request_max, downgrade_task_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid budget mode: {mode}") from exc
    return {"status": "configured", "budget": config}


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
async def configure_alerts_webhook(config: WebhookConfig, _: bool = Depends(require_admin_key)):
    """Configure webhook delivery for alerts."""
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
async def clear_cache(_: bool = Depends(require_admin_key)):
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
    endpoint: str = "",
    _: bool = Depends(require_admin_key),
):
    """Log an API request for tracking and analysis."""
    ts = datetime.fromisoformat(timestamp) if timestamp else datetime.now()
    entry = RequestEntry(
        model=model,
        endpoint=endpoint,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost_usd,
        timestamp=ts,
        request_id=request_id or str(uuid.uuid4())[:8],
    )
    request_logger.log(entry)
    check_and_alert(cost_usd, get_daily_spend(), model)
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
    """Retrieve recent API request history with optional filtering."""
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
    _: bool = Depends(require_admin_key),
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
    _: bool = Depends(require_admin_key),
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
            "model", "endpoint", "prompt_tokens", "completion_tokens",
            "total_tokens", "cost_usd", "timestamp", "request_id",
            "status_code", "cache_hit", "cost_saved_usd",
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
        headers={"Content-Disposition": "attachment; filename=tokenwatch_export.csv"},
    )


# --- Model Pricing ---

@router.get("/pricing/{model}")
async def model_pricing(model: str):
    """Look up pricing for any OpenAI model."""
    from src.core.pricing import get_pricing
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


# --- Projects & API Keys ---

@router.post("/projects", response_model=ProjectResponse)
async def create_project(project: ProjectCreate, _: bool = Depends(require_admin_key)):
    """Create a project for grouping usage and API keys."""
    return project_to_dict(project_store.create_project(project.name, project.daily_budget))


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects():
    """List configured projects."""
    return [project_to_dict(project) for project in project_store.list_projects()]


@router.post("/projects/{project_id}/keys", response_model=APIKeyResponse)
async def create_project_key(project_id: str, key: APIKeyCreate, _: bool = Depends(require_admin_key)):
    """Create a project API key. The raw key is only returned once."""
    result = project_store.create_api_key(project_id, key.name)
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


@router.get("/projects/{project_id}/keys")
async def list_project_keys(project_id: str):
    """List key metadata for a project. Raw key secrets are never returned here."""
    if not project_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"keys": project_store.list_api_keys(project_id)}


@router.get("/projects/{project_id}/usage")
async def project_usage(project_id: str):
    """Usage summary for requests tagged with a project API key."""
    if not project_store.get_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project_store.usage(project_id)


# --- OpenAI-Compatible Proxy ---

@proxy_router.post("/v1/chat/completions")
async def proxy_chat_completions(payload: dict[str, Any], request: Request):
    """OpenAI-compatible chat completions proxy."""
    project_key = request.headers.get("x-token-tracker-key") or request.headers.get("x-tokenwatch-key")
    return await proxy_to_openai("/v1/chat/completions", payload, tokenwatch_key=project_key)


@proxy_router.post("/v1/responses")
async def proxy_responses(payload: dict[str, Any], request: Request):
    """OpenAI-compatible Responses API proxy."""
    project_key = request.headers.get("x-token-tracker-key") or request.headers.get("x-tokenwatch-key")
    return await proxy_to_openai("/v1/responses", payload, tokenwatch_key=project_key)


@proxy_router.post("/v1/embeddings")
async def proxy_embeddings(payload: dict[str, Any], request: Request):
    """OpenAI-compatible embeddings proxy."""
    project_key = request.headers.get("x-token-tracker-key") or request.headers.get("x-tokenwatch-key")
    return await proxy_to_openai("/v1/embeddings", payload, tokenwatch_key=project_key)
