# 🛡️ API Sentinel

> Monitor, analyze, and optimize your OpenAI API spend in real-time.  
> Stop burning tokens. Start understanding where every dollar goes.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-129%20passed-brightgreen.svg)]()
[![CI](https://github.com/escipionpedroza147-commits/API-Sentinel/actions/workflows/tests.yml/badge.svg)](https://github.com/escipionpedroza147-commits/API-Sentinel/actions/workflows/tests.yml)

## The Problem

Enterprise teams spend thousands on OpenAI APIs with zero visibility into where the money goes. Prompts are bloated, responses are uncached, and nobody knows a single request just cost $5 until the monthly bill arrives.

## The Solution

API Sentinel sits between your application and OpenAI. It analyzes every request for cost, efficiency, and waste — then gives you the data to fix it.

### What It Does

- **💰 Real-Time Cost Tracking** — Know exactly what every request costs, broken down by model, tier, and endpoint
- **🔍 Prompt Analysis** — Detect redundancy, waste, and optimization opportunities before spending tokens
- **🗜️ Auto-Compression** — Remove whitespace bloat, merge system messages, eliminate duplicate content
- **💾 Response Caching** — Identical prompts return cached responses at zero token cost (LRU + TTL)
- **⚡ Token-Aware Rate Limiting** — Track both RPM and TPM to prevent 429 errors before they happen
- **🚨 Budget Alerts** — Three-tier alerting (info/warning/critical) with webhook support for Slack/Discord
- **📊 Live Dashboard** — Real-time spend, cache stats, top models, and recent alerts at `/dashboard`
- **📜 Request History** — Log every API call and query history with model/date filters
- **📤 Data Export** — Export request history as CSV or JSON for analysis in external tools
- **💡 Model Recommendations** — Automatically suggest cheaper models that can handle the same task
- **🐳 Docker Ready** — One-command deployment with Docker Compose

## Quick Start

```bash
git clone https://github.com/escipionpedroza147-commits/API-Sentinel.git
cd API-Sentinel
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Server at `http://localhost:8000` — Interactive docs at `/docs`.

### Docker

```bash
# Build and run
docker compose up -d

# Or build manually
docker build -t api-sentinel .
docker run -p 8000:8000 --env-file .env api-sentinel
```

## API Endpoints (20 Total)

### Cost Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/estimate/cost` | Pre-request cost estimate with cheaper model suggestions |
| `POST` | `/api/v1/estimate/batch` | Batch cost estimation for planning |
| `GET` | `/api/v1/pricing/{model}` | Look up any model's pricing |
| `GET` | `/api/v1/pricing` | Full pricing table (37+ models) |

### Prompt Optimization
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyze/prompt` | Detect waste, redundancy, and suggest optimizations |
| `POST` | `/api/v1/optimize/prompt` | Auto-compress prompts and return savings |

### Request Logging & History
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/log` | Log an API request (model, tokens, cost, timestamp) |
| `GET` | `/api/v1/history` | Query request history with model/date filters |

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
| `GET` | `/api/v1/health` | System health with cache stats |
| `GET` | `/api/v1/cache/stats` | Cache hit rate and savings |
| `POST` | `/api/v1/cache/clear` | Flush response cache |
| `GET` | `/api/v1/rate-limit/status` | Current RPM/TPM utilization |
| `POST` | `/api/v1/rate-limit/check` | Pre-flight rate limit check |

### Dashboard
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/dashboard` | Live HTML dashboard with spend, cache, and alerts |

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
openai-api-sentinel/
├── main.py                          # FastAPI server with lifespan + dashboard
├── config/
│   └── settings.py                  # Env-based configuration
├── src/
│   ├── api/
│   │   └── routes.py                # 20 API endpoints
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
│       ├── analytics.py             # Usage aggregation & forecasting
│       └── request_logger.py        # In-memory request log with filtering
├── templates/
│   └── dashboard.html               # Live HTML dashboard
├── tests/                           # 129 tests across 11 test files
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

All 129 tests run offline — no API keys required.

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
