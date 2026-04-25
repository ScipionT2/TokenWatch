# 🛡️ API Sentinel

> Monitor, analyze, and optimize your OpenAI API spend in real-time.  
> Stop burning tokens. Start understanding where every dollar goes.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-77%20passed-brightgreen.svg)]()

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
- **📊 Usage Analytics** — Dashboards, forecasting, and cost-per-model breakdowns
- **💡 Model Recommendations** — Automatically suggest cheaper models that can handle the same task

## Quick Start

```bash
git clone https://github.com/escipionpedroza147-commits/API-Sentinel.git
cd API-Sentinel
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Server at `http://localhost:8000` — Interactive docs at `/docs`.

## API Endpoints (14 Total)

### Cost Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/estimate/cost` | Pre-request cost estimate with cheaper model suggestions |
| `POST` | `/api/v1/estimate/batch` | Batch cost estimation for planning |
| `GET` | `/api/v1/pricing/{model}` | Look up any model's pricing |
| `GET` | `/api/v1/pricing` | Full pricing table (30+ models) |

### Prompt Optimization
| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyze/prompt` | Detect waste, redundancy, and suggest optimizations |
| `POST` | `/api/v1/optimize/prompt` | Auto-compress prompts and return savings |

### Analytics & Alerts
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/analytics/usage` | Usage breakdown by time window and model |
| `GET` | `/api/v1/analytics/forecast` | Projected monthly/yearly spend |
| `GET` | `/api/v1/analytics/alerts` | Recent cost alerts |

### Infrastructure
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | System health with cache stats |
| `GET` | `/api/v1/cache/stats` | Cache hit rate and savings |
| `POST` | `/api/v1/cache/clear` | Flush response cache |
| `GET` | `/api/v1/rate-limit/status` | Current RPM/TPM utilization |
| `POST` | `/api/v1/rate-limit/check` | Pre-flight rate limit check |

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

## Example: Optimize a Bloated Prompt

```bash
curl -X POST http://localhost:8000/api/v1/analyze/prompt \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-5",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant. Please be very helpful and thorough..."},
      {"role": "system", "content": "Also remember to be concise..."},
      {"role": "user", "content": "Hello\n\n\n\n\nworld"}
    ]
  }'
```

Detects: multiple system messages, excessive whitespace, potential token waste.

## Architecture

```
openai-api-sentinel/
├── main.py                          # FastAPI server with lifespan
├── config/
│   └── settings.py                  # Env-based configuration
├── src/
│   ├── api/
│   │   └── routes.py                # 14 API endpoints
│   ├── core/
│   │   ├── pricing.py               # 30+ model pricing engine
│   │   ├── token_counter.py         # tiktoken-backed token counting
│   │   ├── prompt_optimizer.py      # Waste detection & compression
│   │   ├── cache.py                 # LRU response cache with TTL
│   │   └── alerts.py               # Three-tier budget alerting
│   ├── middleware/
│   │   └── rate_limiter.py          # Token-aware RPM/TPM limiter
│   ├── models/
│   │   └── schemas.py               # Pydantic v2 schemas
│   └── services/
│       └── analytics.py             # Usage aggregation & forecasting
├── tests/                           # 77 tests across 7 test files
│   ├── test_pricing.py              # 16 tests
│   ├── test_token_counter.py        # 10 tests
│   ├── test_cache.py                # 9 tests
│   ├── test_alerts.py               # 7 tests
│   ├── test_prompt_optimizer.py     # 7 tests
│   ├── test_rate_limiter.py         # 6 tests
│   └── test_api.py                  # 22 tests
├── requirements.txt
└── LICENSE
```

## Pricing Engine

Covers 30+ OpenAI models with exact per-token pricing:

| Tier | Models | Input/1M | Output/1M |
|------|--------|----------|-----------|
| Flagship | gpt-5, gpt-5.5, o3-pro | $1.25-$30 | $8-$180 |
| Standard | gpt-5-mini, o4-mini | $0.25-$1.10 | $2-$4.40 |
| Economy | gpt-5-nano, gpt-4o-mini | $0.05-$0.20 | $0.40-$1.25 |
| Embedding | text-embedding-3-* | $0.02-$0.13 | — |

## Running Tests

```bash
python -m pytest tests/ -v
```

All 77 tests run offline — no API keys required.

## Use Cases

- **Enterprise Cost Control** — Real-time spend tracking with budget alerts
- **Prompt Engineering** — Measure and optimize prompt efficiency
- **API Gateway** — Centralized monitoring for multi-team OpenAI usage
- **CI/CD Integration** — Pre-commit prompt analysis to catch cost regressions
- **FinOps for AI** — The missing observability layer for LLM spend

## License

MIT — see [LICENSE](LICENSE).

## Contact

**Escipion Pedroza**  
GitHub: [@escipionpedroza147-commits](https://github.com/escipionpedroza147-commits)
