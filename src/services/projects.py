"""Project and Token-Tracker API key management."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config import settings
from src.services.request_logger import request_logger


@dataclass
class Project:
    id: str
    name: str
    daily_budget: Optional[float]
    created_at: datetime


@dataclass
class ProjectAPIKey:
    id: str
    project_id: str
    name: str
    key_hash: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


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


class ProjectStore:
    """SQLite-backed projects and API keys."""

    def __init__(self, database_url: str = None):
        self._db_path = _database_path(database_url or settings.database_url)
        self._ensure_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    daily_budget REAL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS project_api_keys (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()

    @staticmethod
    def _hash_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    def create_project(self, name: str, daily_budget: Optional[float] = None) -> Project:
        project = Project(
            id=f"proj_{secrets.token_hex(6)}",
            name=name,
            daily_budget=daily_budget,
            created_at=datetime.now(),
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, name, daily_budget, created_at) VALUES (?, ?, ?, ?)",
                (project.id, project.name, project.daily_budget, project.created_at.isoformat()),
            )
            conn.commit()
        return project

    def list_projects(self) -> list[Project]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [self._row_to_project(row) for row in rows]

    def get_project(self, project_id: str) -> Optional[Project]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._row_to_project(row) if row else None

    def create_api_key(self, project_id: str, name: str = "default") -> Optional[dict]:
        if not self.get_project(project_id):
            return None
        raw_key = f"tw_{secrets.token_urlsafe(32)}"
        key = ProjectAPIKey(
            id=f"key_{secrets.token_hex(6)}",
            project_id=project_id,
            name=name,
            key_hash=self._hash_key(raw_key),
            created_at=datetime.now(),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO project_api_keys (id, project_id, name, key_hash, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (key.id, key.project_id, key.name, key.key_hash, key.created_at.isoformat(), None),
            )
            conn.commit()
        return {
            "id": key.id,
            "project_id": key.project_id,
            "name": key.name,
            "api_key": raw_key,
            "created_at": key.created_at.isoformat(),
        }

    def list_api_keys(self, project_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, project_id, name, created_at, last_used_at FROM project_api_keys WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def authenticate(self, api_key: str) -> Optional[dict]:
        key_hash = self._hash_key(api_key)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT k.id AS key_id, k.name AS key_name, k.project_id, p.name AS project_name
                FROM project_api_keys k
                JOIN projects p ON p.id = k.project_id
                WHERE k.key_hash = ?
                """,
                (key_hash,),
            ).fetchone()
            if not row:
                return None
            now = datetime.now().isoformat()
            conn.execute("UPDATE project_api_keys SET last_used_at = ? WHERE id = ?", (now, row["key_id"]))
            conn.commit()
        return dict(row)

    def usage(self, project_id: str) -> dict:
        entries = [e for e in request_logger.entries() if (e.metadata or {}).get("project_id") == project_id]
        total_cost = round(sum(e.cost_usd for e in entries), 6)
        total_tokens = sum(e.total_tokens for e in entries)
        by_model: dict[str, dict] = {}
        for entry in entries:
            bucket = by_model.setdefault(entry.model, {"requests": 0, "tokens": 0, "cost_usd": 0.0})
            bucket["requests"] += 1
            bucket["tokens"] += entry.total_tokens
            bucket["cost_usd"] += entry.cost_usd
        for bucket in by_model.values():
            bucket["cost_usd"] = round(bucket["cost_usd"], 6)
        return {
            "project_id": project_id,
            "total_requests": len(entries),
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost,
            "by_model": by_model,
        }

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM project_api_keys")
            conn.execute("DELETE FROM projects")
            conn.commit()

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            daily_budget=row["daily_budget"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


def project_to_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "daily_budget": project.daily_budget,
        "created_at": project.created_at.isoformat(),
    }


project_store = ProjectStore()
