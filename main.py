"""API Sentinel — monitor, optimize, and control your OpenAI API spend."""

import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from config import settings
from src.api.routes import router
from src.core.alerts import get_alert_history, get_daily_spend
from src.core.cache import response_cache
from src.services.analytics import get_usage_summary


logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("API Sentinel starting up")
    logger.info(f"Daily budget: ${settings.alert_daily_budget:.2f}")
    logger.info(f"Rate limits: {settings.rate_limit_rpm} RPM / {settings.rate_limit_tpm} TPM")
    if not settings.openai_api_key:
        logger.warning("OPENAI_API_KEY not set — proxy mode unavailable, analysis tools still work")
    logger.info(f"Server ready on {settings.host}:{settings.port}")
    yield
    logger.info("API Sentinel shutting down")


app = FastAPI(
    title="API Sentinel",
    description=(
        "Monitor, analyze, and optimize OpenAI API usage. "
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

# Jinja2 templates for dashboard — use raw Environment to avoid
# Starlette TemplateResponse caching issues on Python 3.14
_templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
_jinja_env = Environment(loader=FileSystemLoader(_templates_dir), autoescape=True)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Live dashboard showing spend, cache stats, top models, and recent alerts."""
    cache_stats = response_cache.stats()
    usage = get_usage_summary(hours=24)
    alerts = get_alert_history(limit=20)

    # Build top models by cost
    top_models = sorted(
        [
            {"name": model, "requests": usage.requests_by_model.get(model, 0), "cost": cost}
            for model, cost in usage.cost_by_model.items()
        ],
        key=lambda m: m["cost"],
        reverse=True,
    )[:10]

    template = _jinja_env.get_template("dashboard.html")
    html = template.render(
        daily_spend=get_daily_spend(),
        budget=settings.alert_daily_budget,
        cache_hit_rate=cache_stats["hit_rate_pct"],
        cache_entries=cache_stats["entries"],
        total_requests=usage.total_requests,
        tokens_saved=cache_stats["total_tokens_saved"],
        cost_saved=cache_stats["total_cost_saved_usd"],
        top_models=top_models,
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
