# 👁️ Token-Tracker

> Monitor, analyze, and optimize your OpenAI API spend in real-time.  
> Stop burning tokens. Start understanding where every dollar goes.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-177%20passed-brightgreen.svg)]()
[![CI](https://github.com/ScipionT2/Token-Tracker/actions/workflows/tests.yml/badge.svg)](https://github.com/ScipionT2/Token-Tracker/actions/workflows/tests.yml)

## The Problem

Enterprise teams spend thousands on OpenAI APIs with zero visibility into where the money goes. Prompts are bloated, responses are uncached, and nobody knows a single request just cost $5 until the monthly bill arrives.

## The Solution

Token-Tracker sits between your application and AI providers. It analyzes every request for cost, efficiency, and waste — then gives you the data to fix it.

### What It Does

- **💰 Real-Time Cost Tracking** — Know exactly what every request costs, broken down by model, tier, and endpoint
- **🔍 Prompt Analysis** — Detect redundancy, waste, and optimization opportunities before spending tokens
- **🗜️ Auto-Compression** — Remove whitespace bloat, merge system messages, eliminate duplicate content
- **💾 Persistent Response Caching** — Identical prompts return cached responses at zero token cost (SQLite-backed LRU + TTL)
- **⚡ Token-Aware Rate Limiting** — Track both RPM and TPM to prevent 429 errors before they happen
- **🚨 Budget Alerts** — Three-tier alerting (info/warning/critical) with webhook support for Slack/Discord
- **🧯 Hard Budget Controls** — Observe, warn, block, or auto-downgrade requests before overspend happens
- **🔌 OpenAI-Compatible Proxy** — Use `/v1/chat/completions`, `/v1/responses`, or `/v1/embeddings` with a base URL swap
- **📊 SaaS-Style Dashboard** — Spend overview, budget status, model breakdown, recommendations, opportunities, recent requests, and alerts at `/dashboard`
- **📜 Persistent Request History** — Log every API call to SQLite and query history with model/date filters
- **🔑 Projects & API Keys** — Group usage by app/client with `X-Token-Tracker-Key` project keys
- **🔐 Optional Admin Protection** — Set `TOKENWATCH_ADMIN_KEY` to lock sensitive control-plane APIs and HTML pages behind `X-Token-Tracker-Admin-Key`
- **🧪 Production Preflight** — CLI/API checks for admin key strength, demo mode, CORS, budget mode, API key readiness, and durable storage
- **📤 Data Export** — Export request history as CSV or JSON for analysis in external tools
- **💡 Smart Model Recommendations** — Task-aware model swaps with risk, savings, monthly/yearly projections, and reasoning
- **🐳 Docker Ready** — One-command deployment with Docker Compose

## Quick Start

```bash
git clone https://github.com/ScipionT2/Token-Tracker.git
cd Token-Tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
tokenwatch init
tokenwatch serve
```

Server at `http://localhost:8000` — Marketing site at `/` — Setup wizard at `/setup` — Dashboard at `/dashboard` — Interactive docs at `/docs`.

For deploys beyond local demo mode, set `TOKENWATCH_ADMIN_KEY` in `.env`. Sensitive admin/control-plane endpoints then require:

```bash
-H "X-Token-Tracker-Admin-Key: your-admin-key"
```

Useful CLI commands:

```bash
tokenwatch init          # create .env from .env.example
tokenwatch demo --reset  # seed realistic dashboard/demo data
tokenwatch status        # print local config, dashboard URL, proxy readiness
tokenwatch serve         # run the FastAPI server
```

### Demo Mode

Want a populated dashboard without sending real OpenAI traffic?

```bash
tokenwatch init
tokenwatch demo --reset
tokenwatch serve
```

Then open:

```txt
http://localhost:8000/dashboard
```

Demo mode creates a sample project, a demo `X-Token-Tracker-Key`, realistic request history, cache-hit data, model cost breakdowns, duplicate prompt signals, and dashboard optimization opportunities.

For hosted read-only demos, set:

```bash
TOKENWATCH_DEMO_MODE=true
TOKENWATCH_SEED_DEMO=true
```

This keeps `/`, `/dashboard`, and `/setup` public but disables browser project/key creation buttons. `TOKENWATCH_SEED_DEMO=true` auto-populates an empty hosted dashboard with realistic demo data. Admin APIs are still protected when `TOKENWATCH_ADMIN_KEY` is set.

### Production Domain

Recommended professional URL setup:

- Landing page + dashboard: `https://token-tracker.dev`
- Optional clean proxy hostname: `https://api.token-tracker.dev/v1`

See [`DOMAIN.md`](DOMAIN.md), [`deploy/cloud-run.md`](deploy/cloud-run.md), `deploy/production.env.example`, and `deploy/token-tracker.example.conf` for DNS, Docker, Cloud Run, and Nginx/HTTPS setup.

Before exposing a public instance, run:

```bash
tokenwatch preflight
```

### Docker

```bash
# Build and run with a persistent Docker volume
docker compose up -d

# Or build manually
docker build -t tokenwatch .
docker run -p 8000:8000 --env-file .env tokenwatch
```

## API Endpoints (36 Total)

### Cost Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/estimate/cost` | Pre-request cost estimate with cheaper model suggestions |
| `POST` | `/api/v1/estimate/batch` | Batch cost estimation for planning |
| `GET` | `/api/v1/pricing/{model}` | Look up any model's pricing |
| `GET` | `/api/v1/pricing` | Full pricing table (37+ models) |
| `POST` | `/api/v1/recommend/model` | Task-aware cheaper model recommendation with risk and savings |

### Prompt Optimization
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyze/prompt` | Detect waste, redundancy, and suggest optimizations |
| `POST` | `/api/v1/optimize/prompt` | Auto-compress prompts and return savings |

### Request Logging & History
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/log` | Log an API request (model, tokens, cost, timestamp) |
| `GET` | `/api/v1/history` | Query persistent request history with model/date filters |

### Budget Controls
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/budget/config` | Get active budget enforcement config |
| `POST` | `/api/v1/budget/config` | Set mode: `observe`, `warn`, `block`, or `downgrade` |

### Projects & API Keys
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/projects` | Create a project/app/client bucket |
| `GET` | `/api/v1/projects` | List projects |
| `POST` | `/api/v1/projects/{id}/keys` | Create a project API key for `X-Token-Tracker-Key` |
| `GET` | `/api/v1/projects/{id}/keys` | List key metadata without exposing secrets |
| `GET` | `/api/v1/projects/{id}/usage` | Project-specific usage summary |

### OpenAI-Compatible Proxy
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/chat/completions` | Proxy chat completions with logging, caching, budgets, and alerts |
| `POST` | `/v1/responses` | Proxy Responses API requests |
| `POST` | `/v1/embeddings` | Proxy embeddings requests |

### Export
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/export/csv` | Export request history as CSV download |
| `GET` | `/api/v1/export/json` | Export request history as JSON |

### Analytics & Alerts
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/analytics/usage` | Usage breakdown by time window and model |
| `GET` | `/api/v1/analytics/forecast` | Projected monthly/yearly spend |
| `GET` | `/api/v1/analytics/alerts` | Recent cost alerts |
| `POST` | `/api/v1/alerts/configure` | Configure webhook URL and threshold for alerts |
| `GET` | `/api/v1/alerts/webhook` | Get current webhook configuration |

### Infrastructure
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/admin/verify` | Verify an admin key and set the browser admin session cookie |
| `GET` | `/api/v1/health` | System health with cache stats, admin auth status, demo mode, and preflight status |
| `GET` | `/api/v1/preflight` | Production-readiness checks; admin protected when `TOKENWATCH_ADMIN_KEY` is set |
| `GET` | `/api/v1/cache/stats` | Cache hit rate and savings |
| `POST` | `/api/v1/cache/clear` | Flush response cache |
| `GET` | `/api/v1/rate-limit/status` | Current RPM/TPM utilization |
| `POST` | `/api/v1/rate-limit/check` | Pre-flight rate limit check |

### Website, Dashboard & Onboarding
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Professional marketing landing page for Token-Tracker |
| `GET` | `/setup` | Onboarding wizard to create a first project/API key and copy proxy setup snippets |
| `GET` | `/dashboard` | Live HTML dashboard with spend, budgets, model costs, recommendations, requests, alerts, project usage, and API key management |

## Example: First App Setup

Open the setup wizard:

```txt
http://localhost:8000/setup
```

Create a project, generate a one-time `X-Token-Tracker-Key`, then use the generated OpenAI-compatible snippet. The dashboard also includes a **Projects & API Keys** panel for creating projects/keys later and copying proxy snippets.

## Example: Analyze Before You Spend

```bash
# Check what a request will cost BEFORE sending it
curl -X POST http://localhost:8000/api/v1/estimate/cost \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain quantum computing in detail."}
    ]
  }'
```

Response:
```json
{
  "model": "gpt-5",
  "model_tier": "flagship",
  "prompt_tokens": 24,
  "estimated_completion_tokens": 24,
  "estimated_cost_usd": 0.00027,
  "cheaper_alternative": {
    "model": "gpt-5-mini",
    "estimated_cost_usd": 0.000054,
    "savings_pct": 80
  }
}
```

## Example: Smart Model Recommendation

```bash
curl -X POST http://localhost:8000/api/v1/recommend/model \
  -H "Content-Type: application/json" \
  -d '{
    "current_model": "gpt-5",
    "task_type": "summarization",
    "prompt_tokens": 2000,
    "completion_tokens": 500,
    "monthly_requests": 10000
  }'
```

Response:
```json
{
  "current_model": "gpt-5",
  "recommended_model": "gpt-5-mini",
  "task_type": "summarization",
  "risk": "low",
  "estimated_savings_pct": 80.0,
  "monthly_savings_estimate": 21.25,
  "yearly_savings_estimate": 255.0,
  "reason": "Summarization usually does not need flagship reasoning."
}
```

## Example: Admin-Protected Control Plane

Local demos are zero-config. For production-ish deployments, add this to `.env`:

```bash
TOKENWATCH_ADMIN_KEY=change-this-long-random-secret
```

Then call sensitive endpoints with the admin header:

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -H "X-Token-Tracker-Admin-Key: change-this-long-random-secret" \
  -d '{"name":"Production App","daily_budget":25}'
```

Protected endpoints include project/key creation, manual request logging, cache clearing, export, budget changes, and alert webhook configuration. `/setup` and `/dashboard` also show an admin login gate when `TOKENWATCH_ADMIN_KEY` is set. The OpenAI-compatible proxy still uses project keys via `X-Token-Tracker-Key`.

For a public hosted demo, add `TOKENWATCH_DEMO_MODE=true`. That makes `/setup` and `/dashboard` visible in read-only mode while admin APIs remain protected.

## Example: Log & Export Requests

```bash
# Log an API request
curl -X POST "http://localhost:8000/api/v1/log?model=gpt-5&prompt_tokens=1000&completion_tokens=500&cost_usd=0.00625"

# Query history filtered by model
curl "http://localhost:8000/api/v1/history?model=gpt-5&limit=10"

# Export as CSV
curl -o export.csv "http://localhost:8000/api/v1/export/csv"

# Export as JSON
curl "http://localhost:8000/api/v1/export/json"
```

## Architecture

```
tokenwatch/
├── main.py                          # FastAPI server with lifespan + dashboard
├── config/
│   └── settings.py                  # Env-based configuration
├── src/
│   ├── api/
│   │   └── routes.py                # Control-plane endpoints + OpenAI-compatible proxy
│   ├── core/
│   │   ├── pricing.py               # 37+ model pricing engine (OpenAI, Claude, Gemini)
│   │   ├── token_counter.py         # tiktoken-backed token counting
│   │   ├── prompt_optimizer.py      # Waste detection & compression
│   │   ├── cache.py                 # LRU response cache with TTL
│   │   └── alerts.py                # Three-tier budget alerting + webhooks
│   ├── middleware/
│   │   └── rate_limiter.py          # Token-aware RPM/TPM limiter
│   ├── models/
│   │   └── schemas.py               # Pydantic v2 schemas
│   └── services/
│       ├── analytics.py             # Usage aggregation & forecasting over request_logger
│       └── request_logger.py        # SQLite-backed request log with filtering
├── templates/
│   ├── index.html                   # Professional marketing landing page
│   ├── setup.html                   # Onboarding wizard
│   └── dashboard.html               # Live HTML dashboard
├── tests/                           # 177 tests across the offline suite
│   ├── test_pricing.py              # 30 tests (incl. Claude/Gemini)
│   ├── test_token_counter.py        # 10 tests
│   ├── test_cache.py                # 9 tests
│   ├── test_alerts.py               # 7 tests
│   ├── test_prompt_optimizer.py     # 7 tests
│   ├── test_rate_limiter.py         # 6 tests
│   ├── test_api.py                  # 22 tests
│   ├── test_dashboard.py            # 6 tests
│   ├── test_webhooks.py             # 9 tests
│   ├── test_request_logger.py       # 16 tests
│   └── test_export.py              # 13 tests
├── .dockerignore                    # Keeps secrets/local DBs out of container build context
├── .github/
│   └── workflows/
│       └── tests.yml                # CI: automated testing on push/PR
├── Dockerfile                       # Python 3.11-slim container
├── docker-compose.yml               # One-command deployment
├── requirements.txt
└── LICENSE
```

## Pricing Engine

Covers 37+ models across OpenAI, Anthropic (Claude), and Google (Gemini):

| Tier | Models | Input/1M | Output/1M |
|------|--------|----------|-----------|
| Flagship | gpt-5, gpt-5.5, o3-pro, claude-4, claude-4.6, gemini-2.5-pro | $1.25-$30 | $8-$180 |
| Standard | gpt-5-mini, o4-mini, claude-4-haiku, gemini-2.0-pro | $0.25-$1.10 | $2-$5 |
| Economy | gpt-5-nano, gpt-4o-mini, gemini-2.5-flash | $0.05-$0.20 | $0.40-$1.25 |
| Embedding | text-embedding-3-* | $0.02-$0.13 | — |

## Running Tests

```bash
python -m pytest tests/ -v
```

All tests run offline — no API keys required.

## Use Cases

- **Enterprise Cost Control** — Real-time spend tracking with budget alerts
- **Prompt Engineering** — Measure and optimize prompt efficiency
- **API Gateway** — Centralized monitoring for multi-team OpenAI usage
- **CI/CD Integration** — Pre-commit prompt analysis to catch cost regressions
- **FinOps for AI** — The missing observability layer for LLM spend
- **Audit & Compliance** — Export request history for cost reporting

## License

MIT — see [LICENSE](LICENSE).

## Contact

**Escipion Pedroza**  
GitHub: [@escipionpedroza147-commits](https://github.com/escipionpedroza147-commits)
