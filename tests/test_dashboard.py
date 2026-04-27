"""Dashboard endpoint tests — HTML rendering and live stats."""

import pytest
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


class TestDashboard:
    def test_dashboard_returns_html(self):
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_dashboard_contains_title(self):
        r = client.get("/dashboard")
        assert "API Sentinel" in r.text

    def test_dashboard_contains_spend_section(self):
        r = client.get("/dashboard")
        assert "Daily Spend" in r.text
        assert "$" in r.text

    def test_dashboard_contains_cache_section(self):
        r = client.get("/dashboard")
        assert "Cache Hit Rate" in r.text

    def test_dashboard_contains_alerts_section(self):
        r = client.get("/dashboard")
        assert "Recent Alerts" in r.text

    def test_dashboard_contains_requests_section(self):
        r = client.get("/dashboard")
        assert "Total Requests" in r.text
