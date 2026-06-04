"""API endpoint tests — full integration without live AI calls."""

import pytest
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


class TestHealth:
    def test_health_ok(self):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["preflight_status"] in {"pass", "warn", "fail"}


    def test_preflight_endpoint_available_without_admin_when_auth_disabled(self):
        r = client.get("/api/v1/preflight")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in {"pass", "warn", "fail"}
        assert "checks" in data


class TestPromptAnalysis:
    def test_analyze_prompt(self):
        r = client.post("/api/v1/analyze/prompt", json={
            "model": "gpt-5",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "What is Python?"},
            ],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["original_tokens"] > 0
        assert data["estimated_cost_original"] > 0

    def test_optimize_prompt(self):
        r = client.post("/api/v1/optimize/prompt", json={
            "model": "gpt-5",
            "messages": [
                {"role": "system", "content": "Rule 1."},
                {"role": "system", "content": "Rule 2."},
                {"role": "user", "content": "Hello\n\n\n\nworld"},
            ],
        })
        assert r.status_code == 200
        data = r.json()
        assert "optimized_messages" in data
        # System messages should be merged
        sys_msgs = [m for m in data["optimized_messages"] if m["role"] == "system"]
        assert len(sys_msgs) == 1


class TestCostEstimation:
    def test_estimate_cost(self):
        r = client.post("/api/v1/estimate/cost", json={
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "Hello world"}],
        })
        assert r.status_code == 200
        data = r.json()
        assert data["model"] == "gpt-5"
        assert data["prompt_tokens"] > 0
        assert data["estimated_cost_usd"] > 0
        assert data["model_tier"] == "flagship"

    def test_estimate_suggests_cheaper(self):
        r = client.post("/api/v1/estimate/cost", json={
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "Simple question"}],
        })
        data = r.json()
        if data.get("cheaper_alternative"):
            assert data["cheaper_alternative"]["savings_pct"] > 0


class TestPricing:
    def test_single_model_pricing(self):
        r = client.get("/api/v1/pricing/gpt-5")
        assert r.status_code == 200
        data = r.json()
        assert data["input_per_1m_tokens"] == 1.25
        assert data["tier"] == "flagship"

    def test_all_pricing(self):
        r = client.get("/api/v1/pricing")
        assert r.status_code == 200
        data = r.json()
        assert "gpt-5" in data
        assert "gpt-5-nano" in data


class TestCache:
    def test_cache_stats(self):
        r = client.get("/api/v1/cache/stats")
        assert r.status_code == 200
        data = r.json()
        assert "entries" in data
        assert "hit_rate_pct" in data

    def test_cache_clear(self):
        r = client.post("/api/v1/cache/clear")
        assert r.status_code == 200


class TestRateLimit:
    def test_rate_limit_status(self):
        r = client.get("/api/v1/rate-limit/status")
        assert r.status_code == 200
        data = r.json()
        assert "current_rpm" in data
        assert "max_rpm" in data

    def test_rate_limit_check(self):
        r = client.post("/api/v1/rate-limit/check?estimated_tokens=500")
        assert r.status_code == 200
        data = r.json()
        assert data["allowed"] is True


class TestAnalytics:
    def test_usage_summary(self):
        r = client.get("/api/v1/analytics/usage")
        assert r.status_code == 200
        data = r.json()
        assert "total_requests" in data
        assert "total_cost_usd" in data

    def test_cost_forecast(self):
        r = client.get("/api/v1/analytics/forecast")
        assert r.status_code == 200
        data = r.json()
        assert "projected_monthly_spend" in data
        assert "recommendation" in data

    def test_alerts(self):
        r = client.get("/api/v1/analytics/alerts")
        assert r.status_code == 200
        data = r.json()
        assert "alerts" in data
