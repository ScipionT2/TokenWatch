"""Webhook notification tests — alert delivery and configuration."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app
from src.core.alerts import (
    check_and_alert,
    reset_daily_spend,
    configure_webhook,
    get_webhook_config,
    _webhook_config,
)
from src.models.schemas import AlertLevel


client = TestClient(app)


class TestWebhookConfiguration:
    def setup_method(self):
        reset_daily_spend()
        # Reset webhook config
        import src.core.alerts as alerts_mod
        alerts_mod._webhook_config = None

    def test_configure_webhook_endpoint(self):
        r = client.post("/api/v1/alerts/configure", json={
            "url": "https://hooks.slack.com/test",
            "threshold": 10.0,
            "enabled": True,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "configured"
        assert data["webhook"]["url"] == "https://hooks.slack.com/test"
        assert data["webhook"]["threshold"] == 10.0

    def test_configure_webhook_minimal(self):
        r = client.post("/api/v1/alerts/configure", json={
            "url": "https://example.com/webhook",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["webhook"]["enabled"] is True

    def test_get_webhook_unconfigured(self):
        r = client.get("/api/v1/alerts/webhook")
        assert r.status_code == 200
        data = r.json()
        assert data["configured"] is False

    def test_get_webhook_after_configure(self):
        client.post("/api/v1/alerts/configure", json={
            "url": "https://hooks.slack.com/test",
        })
        r = client.get("/api/v1/alerts/webhook")
        data = r.json()
        assert data["configured"] is True
        assert data["webhook"]["url"] == "https://hooks.slack.com/test"

    def test_configure_webhook_function(self):
        result = configure_webhook("https://example.com/hook", threshold=5.0)
        assert result["url"] == "https://example.com/hook"
        assert result["threshold"] == 5.0
        assert result["enabled"] is True

    def test_get_webhook_config_returns_none_initially(self):
        config = get_webhook_config()
        assert config is None


class TestWebhookDelivery:
    def setup_method(self):
        reset_daily_spend()
        import src.core.alerts as alerts_mod
        alerts_mod._webhook_config = None

    @patch("src.core.alerts.httpx.Client")
    def test_webhook_fires_on_alert(self, mock_client_cls):
        """Webhook POST should fire when an alert triggers and webhook is configured."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        configure_webhook("https://hooks.slack.com/test", enabled=True)
        # Trigger a warning (expensive request > $5 default)
        alert = check_and_alert(6.00, 0, "gpt-5-pro")
        assert alert is not None
        assert alert.level == AlertLevel.WARNING
        mock_client.post.assert_called_once()

    @patch("src.core.alerts.httpx.Client")
    def test_webhook_not_fired_when_disabled(self, mock_client_cls):
        """No webhook call when webhook is disabled."""
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

        configure_webhook("https://hooks.slack.com/test", enabled=False)
        check_and_alert(6.00, 0, "gpt-5-pro")
        mock_client.post.assert_not_called()

    def test_custom_threshold_triggers_alert(self):
        """Custom webhook threshold should fire alerts at lower spend."""
        configure_webhook("https://example.com/hook", threshold=2.0, enabled=True)
        # Spend $3 total (3 x $1) — above custom threshold of $2
        check_and_alert(1.00, 0, "gpt-5")
        check_and_alert(1.00, 0, "gpt-5")
        alert = check_and_alert(1.00, 0, "gpt-5")
        assert alert is not None
        assert "threshold exceeded" in alert.message.lower() or "custom" in alert.message.lower()
