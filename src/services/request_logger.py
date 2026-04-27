"""Request logging service — record and query API request history.

Stores requests in-memory with support for model/date filtering.
In production, swap for a persistent store (PostgreSQL, TimescaleDB, etc.).
"""

from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict


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


class RequestLogger:
    """In-memory request log with filtering support."""

    def __init__(self, max_entries: int = 10_000):
        self._entries: list[RequestEntry] = []
        self._max_entries = max_entries

    def log(self, entry: RequestEntry) -> RequestEntry:
        """Record a request. Evicts oldest entries when at capacity."""
        if len(self._entries) >= self._max_entries:
            self._entries = self._entries[-(self._max_entries // 2):]
        self._entries.append(entry)
        return entry

    def get_history(
        self,
        limit: int = 50,
        model: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[dict]:
        """Retrieve recent entries with optional filtering.
        
        Args:
            limit: Maximum entries to return (most recent first).
            model: Filter by model name (case-insensitive partial match).
            start_date: Only entries after this timestamp.
            end_date: Only entries before this timestamp.
        
        Returns:
            List of request entries as dicts, newest first.
        """
        filtered = self._entries

        if model:
            model_lower = model.lower()
            filtered = [e for e in filtered if model_lower in e.model.lower()]

        if start_date:
            filtered = [e for e in filtered if e.timestamp >= start_date]

        if end_date:
            filtered = [e for e in filtered if e.timestamp <= end_date]

        # Return newest first, limited
        result = list(reversed(filtered[-limit:]))
        return [self._to_dict(e) for e in result]

    def count(self) -> int:
        """Total logged entries."""
        return len(self._entries)

    def total_cost(self) -> float:
        """Sum of all logged request costs."""
        return round(sum(e.cost_usd for e in self._entries), 6)

    def clear(self) -> int:
        """Clear all entries. Returns count cleared."""
        count = len(self._entries)
        self._entries.clear()
        return count

    def _to_dict(self, entry: RequestEntry) -> dict:
        """Convert entry to serializable dict."""
        return {
            "model": entry.model,
            "prompt_tokens": entry.prompt_tokens,
            "completion_tokens": entry.completion_tokens,
            "total_tokens": entry.total_tokens,
            "cost_usd": entry.cost_usd,
            "timestamp": entry.timestamp.isoformat(),
            "request_id": entry.request_id,
            "metadata": entry.metadata,
        }


# Singleton instance
request_logger = RequestLogger()
