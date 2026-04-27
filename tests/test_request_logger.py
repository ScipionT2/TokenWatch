"""Request logging and history tests — record and query API requests."""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from main import app
from src.services.request_logger import request_logger, RequestEntry


client = TestClient(app)


class TestLogEndpoint:
    def setup_method(self):
        request_logger.clear()

    def test_log_request(self):
        r = client.post("/api/v1/log", params={
            "model": "gpt-5",
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "cost_usd": 0.0025,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "logged"
        assert data["total_logged"] == 1

    def test_log_with_custom_timestamp(self):
        r = client.post("/api/v1/log", params={
            "model": "gpt-5-mini",
            "prompt_tokens": 50,
            "completion_tokens": 100,
            "cost_usd": 0.001,
            "timestamp": "2026-04-27T10:00:00",
        })
        assert r.status_code == 200

    def test_log_with_request_id(self):
        r = client.post("/api/v1/log", params={
            "model": "gpt-5",
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "cost_usd": 0.005,
            "request_id": "my-req-123",
        })
        data = r.json()
        assert data["request_id"] == "my-req-123"

    def test_log_increments_count(self):
        for i in range(5):
            client.post("/api/v1/log", params={
                "model": "gpt-5",
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "cost_usd": 0.001,
            })
        r = client.post("/api/v1/log", params={
            "model": "gpt-5",
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "cost_usd": 0.001,
        })
        assert r.json()["total_logged"] == 6


class TestHistoryEndpoint:
    def setup_method(self):
        request_logger.clear()
        # Seed some entries
        models = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5", "o3"]
        for i, model in enumerate(models):
            request_logger.log(RequestEntry(
                model=model,
                prompt_tokens=100 * (i + 1),
                completion_tokens=50 * (i + 1),
                total_tokens=150 * (i + 1),
                cost_usd=0.001 * (i + 1),
                timestamp=datetime(2026, 4, 27, 10, i),
            ))

    def test_history_returns_all(self):
        r = client.get("/api/v1/history")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 5
        assert data["total_logged"] == 5

    def test_history_newest_first(self):
        r = client.get("/api/v1/history")
        entries = r.json()["entries"]
        assert entries[0]["model"] == "o3"  # Last logged

    def test_history_filter_by_model(self):
        r = client.get("/api/v1/history", params={"model": "gpt-5-mini"})
        data = r.json()
        assert data["count"] == 1
        assert data["entries"][0]["model"] == "gpt-5-mini"

    def test_history_filter_by_model_partial(self):
        r = client.get("/api/v1/history", params={"model": "gpt-5"})
        data = r.json()
        # Matches gpt-5, gpt-5-mini, gpt-5-nano
        assert data["count"] == 4

    def test_history_filter_by_date_range(self):
        r = client.get("/api/v1/history", params={
            "start_date": "2026-04-27T10:01:00",
            "end_date": "2026-04-27T10:03:00",
        })
        data = r.json()
        assert data["count"] == 3  # entries at 10:01, 10:02, 10:03

    def test_history_limit(self):
        r = client.get("/api/v1/history", params={"limit": 2})
        data = r.json()
        assert data["count"] == 2

    def test_history_total_cost(self):
        r = client.get("/api/v1/history")
        data = r.json()
        assert data["total_cost_usd"] > 0

    def test_history_empty_when_cleared(self):
        request_logger.clear()
        r = client.get("/api/v1/history")
        data = r.json()
        assert data["count"] == 0
        assert data["total_logged"] == 0


class TestRequestLoggerUnit:
    def setup_method(self):
        request_logger.clear()

    def test_log_and_count(self):
        entry = RequestEntry(
            model="gpt-5",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
        )
        request_logger.log(entry)
        assert request_logger.count() == 1

    def test_total_cost(self):
        for cost in [0.001, 0.002, 0.003]:
            request_logger.log(RequestEntry(
                model="gpt-5",
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
                cost_usd=cost,
            ))
        assert abs(request_logger.total_cost() - 0.006) < 0.0001

    def test_clear(self):
        request_logger.log(RequestEntry(
            model="gpt-5", prompt_tokens=1, completion_tokens=1,
            total_tokens=2, cost_usd=0.001,
        ))
        cleared = request_logger.clear()
        assert cleared == 1
        assert request_logger.count() == 0
