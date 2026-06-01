"""Request logging service — persistent record/query of API usage.

SQLite is the default storage layer so TokenWatch keeps usage history across
process restarts while still remaining zero-config for local development.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config import settings


@dataclass
class RequestEntry:
    """A single logged API request."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: str = ""
    metadata: dict = field(default_factory=dict)
    endpoint: str = ""
    latency_ms: float = 0.0
    status_code: int = 200
    cache_hit: bool = False
    tokens_saved: int = 0
    cost_saved_usd: float = 0.0
    prompt_hash: Optional[str] = None
    user_id: Optional[str] = None


class RequestLogger:
    """Persistent request log with in-memory hot cache and filtering support."""

    def __init__(self, max_entries: int = 10_000, database_url: Optional[str] = None):
        self._entries: list[RequestEntry] = []
        self._max_entries = max_entries
        self._db_path = self._database_path(database_url or settings.database_url)
        self._lock = threading.RLock()
        self._ensure_table()
        self.reload()

    @staticmethod
    def _database_path(database_url: str) -> Path:
        """Resolve a sqlite/sqlite+aiosqlite URL to a local filesystem path."""
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
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    model TEXT NOT NULL,
                    endpoint TEXT DEFAULT '',
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    latency_ms REAL DEFAULT 0,
                    status_code INTEGER DEFAULT 200,
                    cache_hit INTEGER DEFAULT 0,
                    tokens_saved INTEGER DEFAULT 0,
                    cost_saved_usd REAL DEFAULT 0,
                    prompt_hash TEXT,
                    user_id TEXT,
                    metadata_json TEXT DEFAULT '{}'
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_requests_model ON requests(model)")
            conn.commit()

    def reload(self) -> None:
        """Reload entries from SQLite into the hot in-memory cache."""
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM requests ORDER BY timestamp ASC LIMIT ?",
                (self._max_entries,),
            ).fetchall()
            self._entries = [self._row_to_entry(row) for row in rows]

    def log(self, entry: RequestEntry) -> RequestEntry:
        """Record a request. Evicts old hot-cache entries when at capacity."""
        if not entry.request_id:
            entry.request_id = f"req-{int(entry.timestamp.timestamp() * 1000)}-{len(self._entries) + 1}"

        with self._lock:
            self._insert(entry)
            if len(self._entries) >= self._max_entries:
                self._entries = self._entries[-(self._max_entries // 2):]
            self._entries.append(entry)
        return entry

    def _insert(self, entry: RequestEntry) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO requests (
                    request_id, timestamp, model, endpoint, prompt_tokens,
                    completion_tokens, total_tokens, cost_usd, latency_ms,
                    status_code, cache_hit, tokens_saved, cost_saved_usd,
                    prompt_hash, user_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.request_id,
                    entry.timestamp.isoformat(),
                    entry.model,
                    entry.endpoint,
                    entry.prompt_tokens,
                    entry.completion_tokens,
                    entry.total_tokens,
                    entry.cost_usd,
                    entry.latency_ms,
                    entry.status_code,
                    int(entry.cache_hit),
                    entry.tokens_saved,
                    entry.cost_saved_usd,
                    entry.prompt_hash,
                    entry.user_id,
                    json.dumps(entry.metadata or {}, sort_keys=True, default=str),
                ),
            )
            conn.commit()

    def get_history(
        self,
        limit: int = 50,
        model: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """Retrieve recent entries with optional filtering, newest first."""
        filtered = self.entries()

        if model:
            model_lower = model.lower()
            filtered = [e for e in filtered if model_lower in e.model.lower()]

        if start_date:
            filtered = [e for e in filtered if e.timestamp >= start_date]

        if end_date:
            filtered = [e for e in filtered if e.timestamp <= end_date]

        result = list(reversed(filtered[-limit:]))
        return [self._to_dict(e) for e in result]

    def entries(self) -> list[RequestEntry]:
        """Return a copy of logged entries, oldest first."""
        with self._lock:
            return list(self._entries)

    def count(self) -> int:
        """Total logged entries."""
        return len(self._entries)

    def count_today(self) -> int:
        """Requests logged since local midnight."""
        today = datetime.now().date()
        return sum(1 for e in self._entries if e.timestamp.date() == today)

    def total_cost(self) -> float:
        """Sum of all logged request costs."""
        return round(sum(e.cost_usd for e in self._entries), 6)

    def clear(self) -> int:
        """Clear all entries from memory and SQLite. Returns count cleared."""
        with self._lock:
            count = len(self._entries)
            self._entries.clear()
            with self._connect() as conn:
                conn.execute("DELETE FROM requests")
                conn.commit()
            return count

    def _row_to_entry(self, row: sqlite3.Row) -> RequestEntry:
        return RequestEntry(
            request_id=row["request_id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            model=row["model"],
            endpoint=row["endpoint"] or "",
            prompt_tokens=row["prompt_tokens"],
            completion_tokens=row["completion_tokens"],
            total_tokens=row["total_tokens"],
            cost_usd=row["cost_usd"],
            latency_ms=row["latency_ms"] or 0.0,
            status_code=row["status_code"] or 200,
            cache_hit=bool(row["cache_hit"]),
            tokens_saved=row["tokens_saved"] or 0,
            cost_saved_usd=row["cost_saved_usd"] or 0.0,
            prompt_hash=row["prompt_hash"],
            user_id=row["user_id"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def _to_dict(self, entry: RequestEntry) -> dict:
        """Convert entry to serializable dict."""
        return {
            "model": entry.model,
            "endpoint": entry.endpoint,
            "prompt_tokens": entry.prompt_tokens,
            "completion_tokens": entry.completion_tokens,
            "total_tokens": entry.total_tokens,
            "cost_usd": entry.cost_usd,
            "latency_ms": entry.latency_ms,
            "status_code": entry.status_code,
            "cache_hit": entry.cache_hit,
            "tokens_saved": entry.tokens_saved,
            "cost_saved_usd": entry.cost_saved_usd,
            "prompt_hash": entry.prompt_hash,
            "user_id": entry.user_id,
            "timestamp": entry.timestamp.isoformat(),
            "request_id": entry.request_id,
            "metadata": entry.metadata,
        }


# Singleton instance
request_logger = RequestLogger()
