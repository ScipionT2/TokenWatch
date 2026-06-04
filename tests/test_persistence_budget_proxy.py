"""Persistence, analytics unification, budget controls, and proxy tests."""

from datetime import datetime

from fastapi.testclient import TestClient

from main import app
from src.core.budget import configure_budget
from src.services.request_logger import RequestEntry, RequestLogger, request_logger


client = TestClient(app)


class TestPersistence:
    def test_request_logger_persists_to_sqlite(self, tmp_path):
        db_url = f"sqlite:///{tmp_path / 'tokenwatch-test.db'}"
        logger = RequestLogger(database_url=db_url)
        logger.clear()
        logger.log(RequestEntry(
            model="gpt-5",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
            timestamp=datetime(2026, 6, 1, 9, 30),
            request_id="persist-1",
        ))

        reloaded = RequestLogger(database_url=db_url)
        assert reloaded.count() == 1
        assert reloaded.get_history()[0]["request_id"] == "persist-1"


class TestUnifiedAnalytics:
    def setup_method(self):
        request_logger.clear()
        configure_budget("observe")

    def test_logged_request_appears_in_usage_analytics(self):
        r = client.post("/api/v1/log", params={
            "model": "gpt-5",
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "cost_usd": 0.001,
        })
        assert r.status_code == 200

        usage = client.get("/api/v1/analytics/usage").json()
        assert usage["total_requests"] == 1
        assert usage["total_cost_usd"] == 0.001
        assert usage["requests_by_model"]["gpt-5"] == 1

    def test_health_uses_real_logged_count(self):
        client.post("/api/v1/log", params={
            "model": "gpt-5-mini",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "cost_usd": 0.0001,
        })
        health = client.get("/api/v1/health").json()
        assert health["requests_logged_today"] >= 1


class TestBudgetControlsAndProxy:
    def setup_method(self):
        request_logger.clear()
        configure_budget("observe")

    def teardown_method(self):
        configure_budget("observe")

    def test_budget_config_endpoint(self):
        r = client.post("/api/v1/budget/config", params={
            "mode": "warn",
            "daily_budget": 1.23,
            "per_request_max": 0.45,
        })
        assert r.status_code == 200
        data = r.json()["budget"]
        assert data["mode"] == "warn"
        assert data["daily_budget"] == 1.23
        assert data["per_request_max"] == 0.45

    def test_proxy_blocks_when_budget_exceeded_before_provider_call(self):
        configure_budget("block", daily_budget=0.000001, per_request_max=0.000001)
        r = client.post("/v1/chat/completions", json={
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "Explain Token-Tracker in detail."}],
        })
        assert r.status_code == 402
        detail = r.json()["detail"]
        assert detail["error"] == "budget_blocked"
        assert detail["tokenwatch_metadata"]["budget"]["action"] == "block"

    def test_proxy_downgrades_before_missing_key_error(self):
        configure_budget("downgrade", daily_budget=0.000001, per_request_max=0.000001)
        r = client.post("/v1/chat/completions", json={
            "model": "gpt-5",
            "messages": [{"role": "user", "content": "Simple question"}],
        })
        assert r.status_code in {402, 503}
        detail = r.json()["detail"]
        if r.status_code == 503:
            budget = detail["tokenwatch_metadata"]["budget"]
            assert budget["action"] == "downgrade"
            assert budget["model"] == "gpt-5-mini"
