from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain import EvidenceRecord, RunCheckpoint, RunEvent


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RunStore:
    """Thread-safe SQLite store for run checkpoints, timeline events, and audit evidence."""

    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            raw_url = os.getenv("DATABASE_URL", "sqlite:///./agentic_engineer.db")
            if raw_url.startswith("sqlite:///"):
                db_path = raw_url.replace("sqlite:///", "", 1)
            else:
                db_path = "agentic_engineer.db"
        self.db_path = Path(db_path).resolve()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    repository TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    passed INTEGER NOT NULL,
                    data_json TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_checkpoint(self, checkpoint: RunCheckpoint) -> None:
        now = _utc_now_iso()
        if not checkpoint.created_at:
            checkpoint.created_at = now
        checkpoint.updated_at = now

        checkpoint_json = checkpoint.model_dump_json()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, title, description, repository, status, created_at, updated_at, checkpoint_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    checkpoint_json=excluded.checkpoint_json
            """,
                (
                    checkpoint.run_id,
                    checkpoint.task.title,
                    checkpoint.task.description,
                    checkpoint.task.repository,
                    checkpoint.status.value,
                    checkpoint.created_at,
                    checkpoint.updated_at,
                    checkpoint_json,
                ),
            )
            conn.commit()

    def get_checkpoint(self, run_id: str) -> RunCheckpoint | None:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT checkpoint_json FROM runs WHERE run_id = ?", (run_id,))
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row["checkpoint_json"])
            return RunCheckpoint.model_validate(data)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT run_id, title, description, repository, status, created_at, updated_at
                FROM runs
                ORDER BY updated_at DESC
                LIMIT ?
            """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def append_event(self, run_id: str, event: RunEvent) -> None:
        timestamp = event.timestamp or _utc_now_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO events (run_id, sequence, status, message, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (run_id, event.sequence, event.status.value, event.message, timestamp),
            )
            conn.commit()

    def append_evidence(self, run_id: str, record: EvidenceRecord) -> None:
        timestamp = record.timestamp or _utc_now_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO evidence (run_id, source, category, summary, passed, data_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    run_id,
                    record.source,
                    record.category,
                    record.summary,
                    1 if record.passed else 0,
                    json.dumps(record.data),
                    timestamp,
                ),
            )
            conn.commit()


_default_store: RunStore | None = None


def get_default_store() -> RunStore:
    global _default_store
    if _default_store is None:
        _default_store = RunStore()
    return _default_store
