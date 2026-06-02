"""Admin-key protection tests for sensitive TokenWatch control-plane endpoints."""

from fastapi.testclient import TestClient

from config import settings
from main import app
from src.services.projects import project_store
from src.services.request_logger import request_logger


client = TestClient(app)


class TestAdminAuth:
    def setup_method(self):
        project_store.clear()
        request_logger.clear()
        self._previous_key = settings.tokenwatch_admin_key
        settings.tokenwatch_admin_key = "test-admin-key"

    def teardown_method(self):
        settings.tokenwatch_admin_key = self._previous_key

    def test_health_reports_admin_auth_enabled(self):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["admin_auth_enabled"] is True

    def test_sensitive_endpoint_rejects_missing_admin_key(self):
        r = client.post("/api/v1/projects", json={"name": "Blocked"})
        assert r.status_code == 401
        assert r.json()["detail"]["error"] == "admin_key_required"

    def test_sensitive_endpoint_rejects_wrong_admin_key(self):
        r = client.post(
            "/api/v1/projects",
            headers={"X-TokenWatch-Admin-Key": "wrong"},
            json={"name": "Blocked"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["error"] == "admin_key_required"

    def test_sensitive_endpoint_accepts_valid_admin_key(self):
        r = client.post(
            "/api/v1/projects",
            headers={"X-TokenWatch-Admin-Key": "test-admin-key"},
            json={"name": "Allowed"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Allowed"

    def test_public_read_endpoint_stays_open(self):
        r = client.get("/api/v1/projects")
        assert r.status_code == 200
        assert r.json() == []

    def test_openai_proxy_still_uses_project_key_not_admin_key(self):
        settings.tokenwatch_admin_key = ""
        project = client.post("/api/v1/projects", json={"name": "Proxy App"}).json()
        key = client.post(f"/api/v1/projects/{project['id']}/keys", json={"name": "dev"}).json()["api_key"]
        settings.tokenwatch_admin_key = "test-admin-key"

        r = client.post(
            "/v1/chat/completions",
            headers={"X-TokenWatch-Key": key},
            json={"model": "gpt-5", "messages": [{"role": "user", "content": "hello"}]},
        )
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "OPENAI_API_KEY not configured"
