"""Response cache — identical prompts shouldn't cost you twice.

SQLite-backed LRU cache with TTL. The key insight: many applications send the
same prompt repeatedly (retries, polling, batch processing with identical
context), and those repeats should not burn tokens.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config import settings


@dataclass
class CacheEntry:
    response: dict
    tokens_saved: int
    cost_saved: float
    created_at: float
    hits: int = 0


class ResponseCache:
    """SQLite-backed LRU cache with TTL for AI API responses."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = None, database_url: str = None, persistent: bool = False):
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds or settings.cache_ttl_seconds
        self._persistent = persistent
        self._db_path = self._database_path(database_url or settings.database_url)
        self._total_hits = 0
        self._total_misses = 0
        self._total_tokens_saved = 0
        self._total_cost_saved = 0.0
        if self._persistent:
            self._ensure_table()
            self._load()

    @staticmethod
    def _database_path(database_url: str) -> Path:
        if database_url.startswith("sqlite+aiosqlite:///"):
            raw = database_url.removeprefix("sqlite+aiosqlite:///")
        elif database_url.startswith("sqlite:///"):
            raw = database_url.removeprefix("sqlite:///")
        else:
            parsed = urlparse(database_url)
            raw = parsed.path.lstrip("/") if parsed.scheme.startswith("sqlite") else "tokenwatch.db"
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    cache_key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    tokens_saved INTEGER NOT NULL,
                    cost_saved REAL NOT NULL,
                    created_at REAL NOT NULL,
                    hits INTEGER DEFAULT 0
                )
                """
            )
            conn.commit()

    def _load(self) -> None:
        now = time.time()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM cache_entries ORDER BY created_at ASC LIMIT ?",
                (self._max_size,),
            ).fetchall()
        for row in rows:
            if now - row["created_at"] > self._ttl:
                self._delete_key(row["cache_key"])
                continue
            self._cache[row["cache_key"]] = CacheEntry(
                response=json.loads(row["response_json"]),
                tokens_saved=row["tokens_saved"],
                cost_saved=row["cost_saved"],
                created_at=row["created_at"],
                hits=row["hits"] or 0,
            )

    def _delete_key(self, key: str) -> None:
        if not self._persistent:
            return
        with self._connect() as conn:
            conn.execute("DELETE FROM cache_entries WHERE cache_key = ?", (key,))
            conn.commit()

    def _make_key(self, model: str, messages: list[dict], temperature: float = None) -> str:
        """Deterministic cache key from request parameters."""
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

        if time.time() - entry.created_at > self._ttl:
            del self._cache[key]
            self._delete_key(key)
            self._total_misses += 1
            return None

        self._cache.move_to_end(key)
        entry.hits += 1
        self._total_hits += 1
        self._total_tokens_saved += entry.tokens_saved
        self._total_cost_saved += entry.cost_saved
        if self._persistent:
            with self._connect() as conn:
                conn.execute("UPDATE cache_entries SET hits = ? WHERE cache_key = ?", (entry.hits, key))
                conn.commit()

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
        if temperature is not None and temperature > 0.5:
            return

        key = self._make_key(model, messages, temperature)

        if len(self._cache) >= self._max_size:
            old_key, _ = self._cache.popitem(last=False)
            self._delete_key(old_key)

        entry = CacheEntry(
            response=response,
            tokens_saved=tokens_used,
            cost_saved=cost,
            created_at=time.time(),
        )
        self._cache[key] = entry
        if self._persistent:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO cache_entries
                    (cache_key, response_json, tokens_saved, cost_saved, created_at, hits)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, json.dumps(response, sort_keys=True, default=str), tokens_used, cost, entry.created_at, 0),
                )
                conn.commit()

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
        if self._persistent:
            with self._connect() as conn:
                conn.execute("DELETE FROM cache_entries")
                conn.commit()
        return count


# Singleton instance
response_cache = ResponseCache(persistent=True)
