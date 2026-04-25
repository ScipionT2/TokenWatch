"""Alert system tests — budget enforcement must be reliable."""

import pytest
from src.core.alerts import check_and_alert, get_alert_history, reset_daily_spend, get_daily_spend
from src.models.schemas import AlertLevel


class TestAlerts:
    def setup_method(self):
        reset_daily_spend()

    def test_no_alert_under_budget(self):
        alert = check_and_alert(0.50, 0.50, "gpt-5-nano")
        assert alert is None

    def test_warning_on_expensive_request(self):
        # Default per-request max is $5.00
        alert = check_and_alert(6.00, 6.00, "gpt-5-pro")
        assert alert is not None
        assert alert.level == AlertLevel.WARNING

    def test_critical_on_budget_exceeded(self):
        # Default daily budget is $50.00
        # Push spend over budget
        for _ in range(51):
            check_and_alert(1.00, 0, "gpt-5")
        alert = check_and_alert(1.00, 0, "gpt-5")
        assert alert is not None
        assert alert.level == AlertLevel.CRITICAL

    def test_info_at_80_percent(self):
        # Push to ~82% of $50 budget = $41
        for _ in range(40):
            check_and_alert(1.00, 0, "gpt-5")
        alert = check_and_alert(1.00, 0, "gpt-5")
        assert alert is not None
        assert alert.level == AlertLevel.INFO

    def test_daily_spend_tracks(self):
        reset_daily_spend()
        check_and_alert(1.50, 0, "gpt-5")
        check_and_alert(2.50, 0, "gpt-5")
        assert get_daily_spend() == 4.00

    def test_alert_history(self):
        reset_daily_spend()
        check_and_alert(6.00, 0, "gpt-5-pro")  # Triggers warning
        history = get_alert_history()
        assert len(history) >= 1

    def test_reset_clears_spend(self):
        check_and_alert(10.00, 0, "gpt-5")
        reset_daily_spend()
        assert get_daily_spend() == 0.0
