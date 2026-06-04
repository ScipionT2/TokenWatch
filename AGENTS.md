# AGENTS.md — Token-Tracker

Token-Tracker is an AI API cost monitoring and control layer. Use **Token-Tracker** in all user-facing copy.

## Product Goal

Help developers see, forecast, and control LLM/API spend with minimal setup.

Core value:
- estimate request cost before spend
- log usage by model/project/user
- detect waste and duplicate prompts
- cache repeat responses
- enforce budgets with observe/warn/block/downgrade modes
- expose an OpenAI-compatible proxy so adoption is a base URL change

## Stack

- Python 3.9+
- FastAPI + uvicorn
- Pydantic v2
- SQLite for local persistence
- httpx for provider forwarding/webhooks
- pytest for tests

## Architecture

- `main.py` — FastAPI app, dashboard, router registration
- `src/api/routes.py` — `/api/v1/*` control-plane routes plus proxy routes when needed
- `src/core/` — pricing, token counting, caching, alerts, budget decisions
- `src/services/` — request logging, analytics, persistence helpers
- `src/models/schemas.py` — API schemas
- `templates/dashboard.html` — server-rendered dashboard
- `tests/` — offline test suite; no live provider calls required

## Coding Rules

- Keep changes focused and test-backed.
- Prefer small modules over bloating `routes.py`.
- No secrets in code; use env vars via `config/settings.py`.
- Tests must pass offline without OpenAI/API keys.
- Default mode should be safe and non-destructive: observe/log before blocking unless configured.
- Preserve compatibility with OpenAI-style clients where possible.

## Validation

Run:

```bash
python3 -m pytest tests/ -q
```

Before claiming completion, also scan docs/UI for legacy branding if editing copy.
