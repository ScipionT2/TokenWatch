"""Smart model recommendation tests."""

from fastapi.testclient import TestClient

from main import app
from src.core.recommendations import recommend_model
from src.models.schemas import TaskType


client = TestClient(app)


class TestRecommendationCore:
    def test_summarization_recommends_mini_with_low_risk(self):
        rec = recommend_model(
            current_model="gpt-5",
            task_type=TaskType.SUMMARIZATION,
            prompt_tokens=2000,
            completion_tokens=500,
            monthly_requests=10_000,
        )
        assert rec["recommended_model"] == "gpt-5-mini"
        assert rec["risk"] == "low"
        assert rec["estimated_savings_pct"] > 0
        assert rec["monthly_savings_estimate"] > 0
        assert "Summarization" in rec["reason"]

    def test_classification_recommends_nano(self):
        rec = recommend_model(
            current_model="gpt-5",
            task_type=TaskType.CLASSIFICATION,
            prompt_tokens=500,
            completion_tokens=20,
            monthly_requests=50_000,
        )
        assert rec["recommended_model"] == "gpt-5-nano"
        assert rec["risk"] == "low"
        assert rec["yearly_savings_estimate"] > 0

    def test_reasoning_does_not_recommend_nano_first(self):
        rec = recommend_model(
            current_model="gpt-5",
            task_type=TaskType.REASONING,
            prompt_tokens=3000,
            completion_tokens=1000,
        )
        assert rec["recommended_model"] == "o4-mini"
        assert rec["risk"] == "medium"

    def test_economy_model_returns_no_change(self):
        rec = recommend_model(
            current_model="gpt-5-nano",
            task_type=TaskType.SIMPLE,
            prompt_tokens=100,
            completion_tokens=50,
        )
        assert rec["recommended_model"] == "gpt-5-nano"
        assert rec["estimated_savings_pct"] == 0.0


class TestRecommendationEndpoint:
    def test_recommend_model_endpoint(self):
        r = client.post("/api/v1/recommend/model", json={
            "current_model": "gpt-5",
            "task_type": "summarization",
            "prompt_tokens": 2000,
            "completion_tokens": 500,
            "monthly_requests": 10000,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["current_model"] == "gpt-5"
        assert data["recommended_model"] == "gpt-5-mini"
        assert data["task_type"] == "summarization"
        assert data["risk"] == "low"
        assert data["monthly_savings_estimate"] > 0
        assert data["alternatives"]

    def test_invalid_task_type_rejected(self):
        r = client.post("/api/v1/recommend/model", json={
            "current_model": "gpt-5",
            "task_type": "brain-surgery",
            "prompt_tokens": 100,
            "completion_tokens": 100,
        })
        assert r.status_code == 422

    def test_negative_tokens_rejected(self):
        r = client.post("/api/v1/recommend/model", json={
            "current_model": "gpt-5",
            "task_type": "chat",
            "prompt_tokens": -1,
            "completion_tokens": 100,
        })
        assert r.status_code == 422
