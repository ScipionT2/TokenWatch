"""Project and TokenWatch API key tests."""

from fastapi.testclient import TestClient

from main import app
from src.core.budget import configure_budget
from src.services.projects import project_store
from src.services.request_logger import RequestEntry, request_logger


client = TestClient(app)


class TestProjects:
    def setup_method(self):
        project_store.clear()
        request_logger.clear()
        configure_budget("observe", daily_budget=50.0, per_request_max=5.0)

    def test_create_and_list_project(self):
        r = client.post("/api/v1/projects", json={"name": "Nova Web", "daily_budget": 12.5})
        assert r.status_code == 200
        project = r.json()
        assert project["id"].startswith("proj_")
        assert project["name"] == "Nova Web"
        assert project["daily_budget"] == 12.5

        listed = client.get("/api/v1/projects").json()
        assert listed[0]["id"] == project["id"]

    def test_create_project_key_returns_secret_once(self):
        project = client.post("/api/v1/projects", json={"name": "Client Bot"}).json()
        r = client.post(f"/api/v1/projects/{project['id']}/keys", json={"name": "dev"})
        assert r.status_code == 200
        key = r.json()
        assert key["api_key"].startswith("tw_")
        assert key["project_id"] == project["id"]

        listed = client.get(f"/api/v1/projects/{project['id']}/keys").json()["keys"]
        assert listed[0]["id"] == key["id"]
        assert "api_key" not in listed[0]

    def test_missing_project_key_creation_404(self):
        r = client.post("/api/v1/projects/proj_missing/keys", json={"name": "dev"})
        assert r.status_code == 404

    def test_project_usage_reads_logged_project_metadata(self):
        project = client.post("/api/v1/projects", json={"name": "Usage App"}).json()
        request_logger.log(RequestEntry(
            model="gpt-5-mini",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            cost_usd=0.001,
            metadata={"project_id": project["id"]},
        ))

        usage = client.get(f"/api/v1/projects/{project['id']}/usage").json()
        assert usage["total_requests"] == 1
        assert usage["total_tokens"] == 150
        assert usage["by_model"]["gpt-5-mini"]["requests"] == 1

    def test_proxy_rejects_invalid_tokenwatch_key(self):
        r = client.post(
            "/v1/chat/completions",
            headers={"X-TokenWatch-Key": "tw_invalid"},
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["error"] == "invalid_tokenwatch_key"

    def test_proxy_accepts_valid_key_until_provider_config_check(self):
        project = client.post("/api/v1/projects", json={"name": "Proxy App"}).json()
        key = client.post(f"/api/v1/projects/{project['id']}/keys", json={"name": "dev"}).json()["api_key"]
        r = client.post(
            "/v1/chat/completions",
            headers={"X-TokenWatch-Key": key},
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "OPENAI_API_KEY not configured"
