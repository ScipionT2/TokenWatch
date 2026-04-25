"""Response cache — identical prompts shouldn't cost you twice.

Simple in-memory LRU cache with TTL. In production, swap for Redis.
The key insight: many applications send the same prompt repeatedly
(retries, polling, batch processing with identical context).
"""

import time
import hashlib
import json
from collections import OrderedDict
from typing import Optional
from dataclasses import dataclass

from config import settings


@dataclass
class CacheEntry:
    response: dict
    tokens_saved: int
    cost_saved: float
    created_at: float
    hits: int = 0


class ResponseCache:
    """LRU cache with TTL for OpenAI API responses."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = None):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds or settings.cache_ttl_seconds
        self._total_hits = 0
        self._total_misses = 0
        self._total_tokens_saved = 0
        self._total_cost_saved = 0.0

    def _make_key(self, model: str, messages: list[dict], temperature: float = None) -> str:
        """Deterministic cache key from request parameters.
        
        Temperature matters: temp=0 is deterministic (cacheable),
        temp>0 introduces randomness (less cacheable but still
        useful for identical retry patterns).
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, model: str, messages: list[dict], temperature: float = None) -> Optional[dict]:
        """Look up a cached response. Returns None on miss."""
        key = self._make_key(model, messages, temperature)

        if key not in self._cache:
            self._total_misses += 1
            return None

        entry = self._cache[key]

        # TTL check
        if time.time() - entry.created_at > self._ttl:
            del self._cache[key]
            self._total_misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        entry.hits += 1
        self._total_hits += 1
        self._total_tokens_saved += entry.tokens_saved
        self._total_cost_saved += entry.cost_saved

        return entry.response

    def put(
        self,
        model: str,
        messages: list[dict],
        response: dict,
        tokens_used: int,
        cost: float,
        temperature: float = None,
    ) -> None:
        """Store a response in the cache."""
        # Only cache deterministic-ish requests
        if temperature is not None and temperature > 0.5:
            return

        key = self._make_key(model, messages, temperature)

        # Evict oldest if at capacity
        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)

        self._cache[key] = CacheEntry(
            response=response,
            tokens_saved=tokens_used,
            cost_saved=cost,
            created_at=time.time(),
        )

    def stats(self) -> dict:
        """Cache performance metrics."""
        total_requests = self._total_hits + self._total_misses
        hit_rate = (self._total_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "entries": len(self._cache),
            "max_size": self._max_size,
            "hit_rate_pct": round(hit_rate, 1),
            "total_hits": self._total_hits,
            "total_misses": self._total_misses,
            "total_tokens_saved": self._total_tokens_saved,
            "total_cost_saved_usd": round(self._total_cost_saved, 4),
        }

    def clear(self) -> int:
        """Flush the cache. Returns number of entries cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count


# Singleton instance
response_cache = ResponseCache()
