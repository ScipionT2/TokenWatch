"""Cache tests — correctness and eviction behavior."""

import time
import pytest
from src.core.cache import ResponseCache


class TestResponseCache:
    def setup_method(self):
        self.cache = ResponseCache(max_size=3, ttl_seconds=60)

    def test_miss_returns_none(self):
        result = self.cache.get("gpt-5", [{"role": "user", "content": "hi"}])
        assert result is None

    def test_hit_returns_response(self):
        messages = [{"role": "user", "content": "hello"}]
        response = {"choices": [{"message": {"content": "hi"}}]}
        self.cache.put("gpt-5", messages, response, tokens_used=10, cost=0.001)

        result = self.cache.get("gpt-5", messages)
        assert result == response

    def test_different_messages_dont_collide(self):
        m1 = [{"role": "user", "content": "hello"}]
        m2 = [{"role": "user", "content": "goodbye"}]
        r1 = {"response": "hi"}
        r2 = {"response": "bye"}

        self.cache.put("gpt-5", m1, r1, 10, 0.001)
        self.cache.put("gpt-5", m2, r2, 10, 0.001)

        assert self.cache.get("gpt-5", m1) == r1
        assert self.cache.get("gpt-5", m2) == r2

    def test_different_models_dont_collide(self):
        messages = [{"role": "user", "content": "hello"}]
        r1 = {"model": "gpt-5"}
        r2 = {"model": "gpt-5-mini"}

        self.cache.put("gpt-5", messages, r1, 10, 0.001)
        self.cache.put("gpt-5-mini", messages, r2, 10, 0.001)

        assert self.cache.get("gpt-5", messages) == r1
        assert self.cache.get("gpt-5-mini", messages) == r2

    def test_eviction_at_capacity(self):
        for i in range(4):
            messages = [{"role": "user", "content": f"msg-{i}"}]
            self.cache.put("gpt-5", messages, {"id": i}, 10, 0.001)

        # First entry should be evicted (max_size=3)
        assert self.cache.get("gpt-5", [{"role": "user", "content": "msg-0"}]) is None
        assert self.cache.get("gpt-5", [{"role": "user", "content": "msg-3"}]) is not None

    def test_ttl_expiry(self):
        cache = ResponseCache(max_size=10, ttl_seconds=1)
        messages = [{"role": "user", "content": "hello"}]
        cache.put("gpt-5", messages, {"ok": True}, 10, 0.001)

        assert cache.get("gpt-5", messages) is not None
        time.sleep(1.1)
        assert cache.get("gpt-5", messages) is None

    def test_high_temperature_not_cached(self):
        messages = [{"role": "user", "content": "be creative"}]
        self.cache.put("gpt-5", messages, {"ok": True}, 10, 0.001, temperature=0.9)
        assert self.cache.get("gpt-5", messages, temperature=0.9) is None

    def test_stats(self):
        messages = [{"role": "user", "content": "hello"}]
        self.cache.put("gpt-5", messages, {"ok": True}, 100, 0.01)
        self.cache.get("gpt-5", messages)  # hit
        self.cache.get("gpt-5", [{"role": "user", "content": "miss"}])  # miss

        stats = self.cache.stats()
        assert stats["entries"] == 1
        assert stats["total_hits"] == 1
        assert stats["total_misses"] == 1
        assert stats["hit_rate_pct"] == 50.0

    def test_clear(self):
        messages = [{"role": "user", "content": "hello"}]
        self.cache.put("gpt-5", messages, {"ok": True}, 10, 0.001)
        cleared = self.cache.clear()
        assert cleared == 1
        assert self.cache.get("gpt-5", messages) is None
