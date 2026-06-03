"""Admin-key protection tests for sensitive TokenWatch control-plane endpoints."""

from fastapi.testclient import TestClient

from config import settings
from main import app
from src.core.auth import admin_session_token
from src.services.projects import project_store
from src.services.request_logger import request_logger


client = TestClient(app)


class TestAdminAuth:
    def setup_method(self):
        client.cookies.clear()
        project_store.clear()
        request_logger.clear()
        self._previous_key = settings.tokenwatch_admin_key
        self._previous_demo_mode = settings.tokenwatch_demo_mode
        settings.tokenwatch_admin_key = "test-admin-key"
        settings.tokenwatch_demo_mode = False

    def teardown_method(self):
        settings.tokenwatch_admin_key = self._previous_key
        settings.tokenwatch_demo_mode = self._previous_demo_mode

    def test_health_reports_admin_auth_enabled(self):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        assert r.json()["admin_auth_enabled"] is True
        assert r.json()["demo_mode"] is False

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

    def test_admin_verify_sets_browser_session_cookie(self):
        r = client.get("/api/v1/admin/verify", headers={"X-TokenWatch-Admin-Key": "test-admin-key"})
        assert r.status_code == 200
        assert r.json()["admin"] is True
        assert "tokenwatch_admin_session" in r.cookies

    def test_dashboard_requires_admin_when_html_gate_enabled(self):
        r = client.get("/dashboard")
        assert r.status_code == 401
        assert "Admin Login" in r.text

    def test_dashboard_accepts_admin_session_cookie(self):
        r = client.get("/dashboard", cookies={"tokenwatch_admin_session": admin_session_token()})
        assert r.status_code == 200
        assert "Daily Spend" in r.text

    def test_setup_query_admin_key_redirects_and_sets_session_cookie(self):
        r = client.get("/setup?admin_key=test-admin-key", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/setup"
        assert "tokenwatch_admin_session" in r.cookies

    def test_demo_mode_keeps_html_pages_public_read_only(self):
        settings.tokenwatch_demo_mode = True
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "Demo: <strong>read-only</strong>" in r.text
        assert "Read-only demo mode" in r.text

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
