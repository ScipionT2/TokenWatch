"""TokenWatch command-line interface.

Provides the simple local developer flow:

    tokenwatch init
    tokenwatch serve
    tokenwatch status
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import uvicorn

from config import settings
from src.core.budget import configure_budget
from src.core.pricing import calculate_cost
from src.core.token_counter import hash_prompt
from src.services.projects import project_store
from src.services.request_logger import RequestEntry, request_logger


ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"


def init_env(env_file: Path = ENV_FILE, env_example: Path = ENV_EXAMPLE) -> str:
    """Create a .env from .env.example if it does not already exist."""
    if env_file.exists():
        return f"TokenWatch already initialized: {env_file}"
    if env_example.exists():
        shutil.copyfile(env_example, env_file)
    else:
        env_file.write_text(
            "OPENAI_API_KEY=\n"
            "HOST=0.0.0.0\n"
            "PORT=8000\n"
            "LOG_LEVEL=info\n"
            "TOKENWATCH_ADMIN_KEY=\n"
            "DATABASE_URL=sqlite+aiosqlite:///./tokenwatch.db\n"
            "BUDGET_MODE=observe\n"
        )
    return f"TokenWatch initialized: {env_file}"


def status_text() -> str:
    """Human-readable local configuration status."""
    has_key = bool(settings.openai_api_key)
    return "\n".join([
        "TokenWatch status",
        f"  Server: http://{settings.host}:{settings.port}",
        f"  Dashboard: http://localhost:{settings.port}/dashboard",
        f"  Docs: http://localhost:{settings.port}/docs",
        f"  Database: {settings.database_url}",
        f"  Budget mode: {settings.budget_mode}",
        f"  Admin API protection: {'enabled' if settings.tokenwatch_admin_key else 'disabled'}",
        f"  OpenAI proxy forwarding: {'ready' if has_key else 'needs OPENAI_API_KEY'}",
    ])


def serve(host: str | None = None, port: int | None = None, reload: bool = False) -> None:
    """Start the TokenWatch FastAPI app."""
    uvicorn.run(
        "main:app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload,
        log_level=settings.log_level,
    )


def seed_demo_data(reset: bool = False) -> str:
    """Seed realistic local demo data for dashboard screenshots and demos."""
    if reset:
        request_logger.clear()
        project_store.clear()

    configure_budget("warn", daily_budget=2.50, per_request_max=0.10)
    project = project_store.create_project("Demo SaaS App", daily_budget=2.50)
    api_key = project_store.create_api_key(project.id, "demo-key")

    now = datetime.now()
    samples = [
        ("gpt-5", "/v1/chat/completions", 3200, 950, "Summarize customer onboarding transcript"),
        ("gpt-5-mini", "/v1/chat/completions", 1400, 420, "Draft support response"),
        ("gpt-5-nano", "/v1/chat/completions", 260, 40, "Classify ticket urgency"),
        ("gpt-5", "/v1/responses", 5200, 1400, "Analyze sales pipeline risks"),
        ("gpt-5-mini", "/v1/chat/completions", 900, 300, "Generate changelog summary"),
        ("gpt-5-nano", "/v1/chat/completions", 260, 40, "Classify ticket urgency"),
        ("gpt-5-mini", "/v1/chat/completions", 1100, 280, "Extract invoice fields"),
        ("gpt-5", "/v1/chat/completions", 2500, 800, "Debug billing reconciliation issue"),
        ("gpt-5-nano", "/v1/embeddings", 700, 0, "Embed help center article"),
        ("gpt-5-mini", "/v1/chat/completions", 1600, 500, "Summarize product feedback"),
    ]

    for i, (model, endpoint, prompt_tokens, completion_tokens, prompt) in enumerate(samples):
        cost = calculate_cost(model, prompt_tokens, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens
        cache_hit = i == 5
        request_logger.log(RequestEntry(
            model=model,
            endpoint=endpoint,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=0.0 if cache_hit else cost,
            timestamp=now - timedelta(minutes=(len(samples) - i) * 18),
            request_id=f"demo-{i + 1}",
            latency_ms=180 + (i * 37),
            status_code=200,
            cache_hit=cache_hit,
            tokens_saved=total_tokens if cache_hit else 0,
            cost_saved_usd=cost if cache_hit else 0.0,
            prompt_hash=hash_prompt([{"role": "user", "content": prompt}]),
            metadata={"project_id": project.id, "project_name": project.name},
        ))

    return "\n".join([
        "TokenWatch demo data seeded.",
        f"  Project: {project.name} ({project.id})",
        f"  Demo API key: {api_key['api_key']}",
        f"  Requests added: {len(samples)}",
        f"  Dashboard: http://localhost:{settings.port}/dashboard",
    ])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tokenwatch", description="TokenWatch local AI API spend control")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Create .env from .env.example")

    serve_parser = sub.add_parser("serve", help="Run the TokenWatch server")
    serve_parser.add_argument("--host", default=None, help="Host to bind, default from .env/HOST")
    serve_parser.add_argument("--port", type=int, default=None, help="Port to bind, default from .env/PORT")
    serve_parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload")

    demo_parser = sub.add_parser("demo", help="Seed realistic local demo data for the dashboard")
    demo_parser.add_argument("--reset", action="store_true", help="Clear request/project data before seeding")

    sub.add_parser("status", help="Print local TokenWatch config/status")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        print(init_env())
        return 0
    if args.command == "serve":
        serve(host=args.host, port=args.port, reload=args.reload)
        return 0
    if args.command == "demo":
        print(seed_demo_data(reset=args.reset))
        return 0
    if args.command == "status":
        print(status_text())
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
