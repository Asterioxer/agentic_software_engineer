from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain import EvidenceRecord, JournalOperation, OperationState, RunCheckpoint, RunEvent


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RunStore:
    """Thread-safe SQLite store for run checkpoints, operation journal, and audit evidence."""

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
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    tool TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    precondition_hash TEXT,
                    postcondition_hash TEXT,
                    state TEXT NOT NULL,
                    execution_attempt INTEGER NOT NULL DEFAULT 1,
                    inputs_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    recovery_status TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ops_run_id ON operations(run_id);")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_ops_idempotency ON operations(idempotency_key);"
            )
            conn.commit()

    # --- Run Checkpoint APIs ---

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

    # --- Operation Journal APIs ---

    def create_operation(self, op: JournalOperation) -> None:
        now = _utc_now_iso()
        created = op.created_at or now
        updated = op.updated_at or now
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO operations (
                    operation_id, run_id, step_id, idempotency_key, tool, input_hash,
                    precondition_hash, postcondition_hash, state, execution_attempt,
                    inputs_json, result_json, error, recovery_status, started_at,
                    completed_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    execution_attempt = operations.execution_attempt + 1,
                    state = excluded.state,
                    updated_at = excluded.updated_at
            """,
                (
                    op.operation_id,
                    op.run_id,
                    op.step_id,
                    op.idempotency_key,
                    op.tool,
                    op.input_hash,
                    op.precondition_hash,
                    op.postcondition_hash,
                    op.state.value,
                    op.execution_attempt,
                    json.dumps(op.inputs),
                    json.dumps(op.result) if op.result else None,
                    op.error,
                    op.recovery_status,
                    op.started_at,
                    op.completed_at,
                    created,
                    updated,
                ),
            )
            conn.commit()

    def update_operation_state(
        self,
        operation_id: str,
        state: OperationState,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        postcondition_hash: str | None = None,
        recovery_status: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        now = _utc_now_iso()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE operations SET
                    state = ?,
                    result_json = CASE WHEN ? IS NOT NULL THEN ? ELSE result_json END,
                    error = CASE WHEN ? IS NOT NULL THEN ? ELSE error END,
                    postcondition_hash = CASE WHEN ? IS NOT NULL THEN ? ELSE postcondition_hash END,
                    recovery_status = CASE WHEN ? IS NOT NULL THEN ? ELSE recovery_status END,
                    completed_at = CASE WHEN ? IS NOT NULL THEN ? ELSE completed_at END,
                    updated_at = ?
                WHERE operation_id = ?
            """,
                (
                    state.value,
                    json.dumps(result) if result is not None else None,
                    json.dumps(result) if result is not None else None,
                    error,
                    error,
                    postcondition_hash,
                    postcondition_hash,
                    recovery_status,
                    recovery_status,
                    completed_at or now,
                    completed_at or now,
                    now,
                    operation_id,
                ),
            )
            conn.commit()

    def get_operation(self, operation_id: str) -> JournalOperation | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM operations WHERE operation_id = ?", (operation_id,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_operation(row)

    def get_operation_by_idempotency_key(self, idempotency_key: str) -> JournalOperation | None:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM operations WHERE idempotency_key = ?", (idempotency_key,)
            )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_operation(row)

    def list_operations_for_run(self, run_id: str) -> list[JournalOperation]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM operations WHERE run_id = ? ORDER BY created_at ASC", (run_id,)
            )
            rows = cursor.fetchall()
            return [self._row_to_operation(row) for row in rows]

    def mark_interrupted_operations(self, run_id: str) -> list[JournalOperation]:
        """Scan for operations that were left in PREPARED or RUNNING and mark them INTERRUPTED."""
        now = _utc_now_iso()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT operation_id FROM operations
                WHERE run_id = ? AND state IN ('prepared', 'running')
            """,
                (run_id,),
            )
            ids = [row["operation_id"] for row in cursor.fetchall()]
            if ids:
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"""
                    UPDATE operations
                    SET state = 'interrupted',
                        recovery_status = 'detected_unclean_termination',
                        updated_at = ?
                    WHERE operation_id IN ({placeholders})
                """,
                    [now, *ids],
                )
                conn.commit()

        return [op for op_id in ids if (op := self.get_operation(op_id))]

    @staticmethod
    def _row_to_operation(row: sqlite3.Row) -> JournalOperation:
        return JournalOperation(
            operation_id=row["operation_id"],
            run_id=row["run_id"],
            step_id=row["step_id"],
            idempotency_key=row["idempotency_key"],
            tool=row["tool"],
            input_hash=row["input_hash"],
            precondition_hash=row["precondition_hash"],
            postcondition_hash=row["postcondition_hash"],
            state=OperationState(row["state"]),
            execution_attempt=row["execution_attempt"],
            inputs=json.loads(row["inputs_json"]) if row["inputs_json"] else {},
            result=json.loads(row["result_json"]) if row["result_json"] else None,
            error=row["error"],
            recovery_status=row["recovery_status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


_default_store: RunStore | None = None


def get_default_store() -> RunStore:
    global _default_store
    if _default_store is None:
        _default_store = RunStore()
    return _default_store
