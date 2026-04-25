"""API Sentinel — monitor, optimize, and control your OpenAI API spend."""

import logging
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from src.api.routes import router


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


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level,
    )
