"""Dashboard endpoint tests — HTML rendering and live stats."""

import pytest
from fastapi.testclient import TestClient
from main import app


client = TestClient(app)


class TestDashboard:
    def test_homepage_returns_marketing_site(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "TokenWatch — AI API spend control" in r.text
        assert "Stop guessing" in r.text
        assert "tokenwatch.dev" in r.text

    def test_dashboard_returns_html(self):
        r = client.get("/dashboard")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_dashboard_contains_title(self):
        r = client.get("/dashboard")
        assert "TokenWatch" in r.text

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

    def test_dashboard_contains_budget_mode(self):
        r = client.get("/dashboard")
        assert "Budget mode" in r.text

    def test_dashboard_contains_smart_recommendation(self):
        r = client.get("/dashboard")
        assert "Smart Recommendation" in r.text

    def test_dashboard_contains_optimization_opportunities(self):
        r = client.get("/dashboard")
        assert "Optimization Opportunities" in r.text

    def test_dashboard_contains_recent_requests_table(self):
        r = client.get("/dashboard")
        assert "Recent Requests" in r.text

    def test_dashboard_contains_model_breakdown(self):
        r = client.get("/dashboard")
        assert "Model Cost Breakdown" in r.text

    def test_setup_returns_html(self):
        r = client.get("/setup")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Setup wizard" in r.text
        assert "Create project + key" in r.text

    def test_dashboard_contains_project_key_management(self):
        r = client.get("/dashboard")
        assert "Projects &amp; API Keys" in r.text or "Projects & API Keys" in r.text
        assert "Create project" in r.text
        assert "Generate" in r.text
