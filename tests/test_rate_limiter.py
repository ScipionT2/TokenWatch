"""Rate limiter tests — must track both RPM and TPM."""

import time
import pytest
from src.middleware.rate_limiter import TokenAwareRateLimiter


class TestTokenAwareRateLimiter:
    def setup_method(self):
        self.limiter = TokenAwareRateLimiter(rpm=3, tpm=1000)

    def test_first_request_allowed(self):
        result = self.limiter.check(100)
        assert result["allowed"] is True

    def test_under_rpm_allowed(self):
        self.limiter.record(100)
        self.limiter.record(100)
        result = self.limiter.check(100)
        assert result["allowed"] is True

    def test_at_rpm_limit_blocked(self):
        for _ in range(3):
            self.limiter.record(100)
        result = self.limiter.check(100)
        assert result["allowed"] is False
        assert "RPM" in result["reason"]

    def test_tpm_limit_blocked(self):
        self.limiter.record(900)
        result = self.limiter.check(200)
        assert result["allowed"] is False
        assert "TPM" in result["reason"]

    def test_stats(self):
        self.limiter.record(500)
        stats = self.limiter.stats()
        assert stats["current_rpm"] == 1
        assert stats["max_rpm"] == 3
        assert stats["current_tpm"] == 500
        assert stats["max_tpm"] == 1000

    def test_window_expires(self):
        limiter = TokenAwareRateLimiter(rpm=1, tpm=1000)
        limiter._window_seconds = 0.5  # Short window for testing
        limiter.record(100)
        result = limiter.check(100)
        assert result["allowed"] is False

        time.sleep(0.6)
        result = limiter.check(100)
        assert result["allowed"] is True
