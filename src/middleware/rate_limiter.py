"""Token-aware rate limiter — prevents 429s before they happen.

Most rate limiters count requests. OpenAI limits by both RPM and TPM.
This limiter tracks both dimensions so you never hit a 429.
"""

import time
import logging
from collections import deque
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class TokenAwareRateLimiter:
    """Sliding window rate limiter tracking both requests and tokens per minute."""

    def __init__(
        self,
        rpm: int = None,
        tpm: int = None,
    ):
        self._rpm = rpm or settings.rate_limit_rpm
        self._tpm = tpm or settings.rate_limit_tpm
        # Sliding window of (timestamp, token_count)
        self._requests: deque[tuple[float, int]] = deque()
        self._window_seconds = 60.0

    def _prune_old(self) -> None:
        """Remove entries older than the sliding window."""
        cutoff = time.time() - self._window_seconds
        while self._requests and self._requests[0][0] < cutoff:
            self._requests.popleft()

    def check(self, estimated_tokens: int = 0) -> dict:
        """Check if a request can proceed without hitting limits.
        
        Returns:
            {"allowed": bool, "wait_seconds": float, "reason": str}
        """
        self._prune_old()

        current_rpm = len(self._requests)
        current_tpm = sum(t for _, t in self._requests)

        # Check RPM
        if current_rpm >= self._rpm:
            oldest = self._requests[0][0]
            wait = self._window_seconds - (time.time() - oldest)
            return {
                "allowed": False,
                "wait_seconds": round(max(0, wait), 2),
                "reason": f"RPM limit ({self._rpm}): {current_rpm} requests in window.",
                "current_rpm": current_rpm,
                "current_tpm": current_tpm,
            }

        # Check TPM
        if current_tpm + estimated_tokens > self._tpm:
            oldest = self._requests[0][0]
            wait = self._window_seconds - (time.time() - oldest)
            return {
                "allowed": False,
                "wait_seconds": round(max(0, wait), 2),
                "reason": f"TPM limit ({self._tpm}): {current_tpm} + {estimated_tokens} tokens exceeds limit.",
                "current_rpm": current_rpm,
                "current_tpm": current_tpm,
            }

        return {
            "allowed": True,
            "wait_seconds": 0,
            "reason": "OK",
            "current_rpm": current_rpm,
            "current_tpm": current_tpm,
        }

    def record(self, tokens: int) -> None:
        """Record a completed request."""
        self._requests.append((time.time(), tokens))

    def stats(self) -> dict:
        """Current rate limiter state."""
        self._prune_old()
        current_rpm = len(self._requests)
        current_tpm = sum(t for _, t in self._requests)
        return {
            "current_rpm": current_rpm,
            "max_rpm": self._rpm,
            "rpm_utilization_pct": round(current_rpm / self._rpm * 100, 1) if self._rpm else 0,
            "current_tpm": current_tpm,
            "max_tpm": self._tpm,
            "tpm_utilization_pct": round(current_tpm / self._tpm * 100, 1) if self._tpm else 0,
        }


# Singleton instance
rate_limiter = TokenAwareRateLimiter()
