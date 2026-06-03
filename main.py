"""TokenWatch — monitor, optimize, and control your AI API spend."""

import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from config import settings
from src.api.routes import proxy_router, router
from src.core.alerts import get_alert_history, get_daily_spend
from src.core.budget import get_budget_config
from src.core.cache import response_cache
from src.core.auth import demo_mode_enabled, require_html_admin
from src.core.recommendations import recommend_model
from src.models.schemas import TaskType
from src.services.analytics import get_usage_summary, get_cost_forecast
from src.services.request_logger import request_logger
from src.services.projects import project_store, project_to_dict


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("TokenWatch starting up")
    logger.info(f"Daily budget: ${settings.alert_daily_budget:.2f}")
    logger.info(f"Rate limits: {settings.rate_limit_rpm} RPM / {settings.rate_limit_tpm} TPM")
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — proxy mode unavailable, analysis tools still work")
    logger.info(f"Server ready on {settings.host}:{settings.port}")
    yield
    logger.info("TokenWatch shutting down")


app = FastAPI(
    title="TokenWatch",
    description=(
        "Monitor, analyze, and optimize AI API usage. "
        "Pre-request cost estimation, prompt optimization, response caching, "
        "token-aware rate limiting, and real-time cost alerts."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(proxy_router)

# Jinja2 templates for dashboard — use raw Environment to avoid
# Starlette TemplateResponse caching issues on Python 3.14
_templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
_jinja_env = Environment(loader=FileSystemLoader(_templates_dir), autoescape=True)


@app.get("/setup", response_class=HTMLResponse)
async def setup(request: Request):
    """Onboarding flow for creating a first project/API key and proxy snippet."""
    gate = require_html_admin(request)
    if gate:
        return gate
    template = _jinja_env.get_template("setup.html")
    return HTMLResponse(content=template.render(
        request=request,
        demo_mode=demo_mode_enabled(),
        admin_auth_enabled=bool(settings.tokenwatch_admin_key),
    ))


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Live dashboard showing spend, budgets, recommendations, requests, and alerts."""
    gate = require_html_admin(request)
    if gate:
        return gate
    cache_stats = response_cache.stats()
    usage = get_usage_summary(hours=24)
    forecast = get_cost_forecast()
    alerts = get_alert_history(limit=20)
    budget_config = get_budget_config()
    recent_requests = request_logger.get_history(limit=10)

    top_models = sorted(
        [
            {
                "name": model,
                "requests": usage.requests_by_model.get(model, 0),
                "cost": cost,
                "share_pct": round((cost / usage.total_cost_usd * 100), 1) if usage.total_cost_usd else 0,
            }
            for model, cost in usage.cost_by_model.items()
        ],
        key=lambda m: m["cost"],
        reverse=True,
    )[:10]

    avg_prompt = max(1, usage.total_prompt_tokens // usage.total_requests) if usage.total_requests else 2000
    avg_completion = max(1, usage.total_completion_tokens // usage.total_requests) if usage.total_requests else 500
    recommendation_model = top_models[0]["name"] if top_models else "gpt-5"
    smart_recommendation = recommend_model(
        current_model=recommendation_model,
        task_type=TaskType.GENERAL,
        prompt_tokens=avg_prompt,
        completion_tokens=avg_completion,
        monthly_requests=max(usage.total_requests * 30, 10_000),
    )

    opportunities = []
    if usage.top_expensive_requests:
        top_request = usage.top_expensive_requests[0]
        opportunities.append({
            "title": "Review expensive requests",
            "detail": f"Top request used {top_request.get('total_tokens', 0)} tokens and cost ${top_request.get('cost_usd', 0):.4f}.",
            "severity": "warning",
        })
    if usage.duplicate_request_count > 0:
        opportunities.append({
            "title": "Duplicate prompts detected",
            "detail": f"{usage.duplicate_request_count} duplicate prompts found in the last 24h. Cache or dedupe them.",
            "severity": "info",
        })
    if usage.total_requests > 10 and cache_stats["hit_rate_pct"] < 20:
        opportunities.append({
            "title": "Cache hit rate is low",
            "detail": "Repeated requests are not hitting cache often. Check temperature and prompt normalization.",
            "severity": "info",
        })
    if smart_recommendation["recommended_model"] != smart_recommendation["current_model"]:
        opportunities.append({
            "title": "Cheaper model available",
            "detail": f"Try {smart_recommendation['recommended_model']} for ~{smart_recommendation['estimated_savings_pct']}% savings.",
            "severity": "success",
        })
    if not opportunities:
        opportunities.append({
            "title": "No major waste detected",
            "detail": "TokenWatch has not found urgent optimization issues in the current window.",
            "severity": "success",
        })

    projects = []
    for project in project_store.list_projects():
        project_dict = project_to_dict(project)
        project_dict["api_keys"] = project_store.list_api_keys(project.id)
        project_dict["usage"] = project_store.usage(project.id)
        projects.append(project_dict)

    template = _jinja_env.get_template("dashboard.html")
    html = template.render(
        daily_spend=get_daily_spend(),
        budget=budget_config["daily_budget"],
        budget_mode=budget_config["mode"],
        per_request_max=budget_config["per_request_max"],
        projects=projects,
        project_count=len(projects),
        admin_auth_enabled=bool(settings.tokenwatch_admin_key),
        demo_mode=demo_mode_enabled(),
        projected_monthly=forecast.projected_monthly_spend,
        projected_yearly=forecast.projected_yearly_spend,
        budget_utilization=forecast.budget_utilization_pct,
        cache_hit_rate=cache_stats["hit_rate_pct"],
        cache_entries=cache_stats["entries"],
        total_requests=usage.total_requests,
        total_tokens=usage.total_tokens,
        total_cost=usage.total_cost_usd,
        duplicate_request_count=usage.duplicate_request_count,
        avg_latency_ms=usage.avg_latency_ms,
        tokens_saved=cache_stats["total_tokens_saved"],
        cost_saved=cache_stats["total_cost_saved_usd"],
        top_models=top_models,
        top_expensive_requests=usage.top_expensive_requests,
        smart_recommendation=smart_recommendation,
        opportunities=opportunities,
        recent_requests=recent_requests,
        alerts=[
            {
                "level": a.level.value,
                "message": a.message,
                "triggered_at": a.triggered_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for a in alerts
        ],
    )
    return HTMLResponse(content=html)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level,
    )
