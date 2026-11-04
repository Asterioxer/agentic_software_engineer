from __future__ import annotations

import json
from pathlib import Path

from starlette.testclient import TestClient

from app.distillation import DatasetExporter
from app.domain import TaskSpec
from app.main import app
from app.policy import ToolPolicy
from app.runner import AgentRun
from app.store import RunStore, get_default_store
from app.tools import build_default_registry


def test_distillation_export_records(tmp_path: Path) -> None:
    db_path = str(tmp_path / "distill.db")
    store = RunStore(db_path)

    # Execute a clean completed task
    task = TaskSpec(
        title="Safe distillation task",
        description="Verify clean extraction into training pairs",
        repository=str(tmp_path),
        dry_run=True,
    )
    run = AgentRun(task, build_default_registry(), ToolPolicy(), store=store)
    res = run.execute()
    assert res["status"] == "completed"

    exporter = DatasetExporter(store=store)
    records = exporter.extract_training_records()
    assert len(records) >= 1

    first = records[0]
    assert "messages" in first
    assert len(first["messages"]) == 3
    assert first["messages"][0]["role"] == "system"
    assert first["messages"][1]["role"] == "user"
    assert "Safe distillation task" in first["messages"][1]["content"]
    assert first["messages"][2]["role"] == "assistant"
    assert "Execution Plan" in first["messages"][2]["content"]
    assert "Verification Evidence" in first["messages"][2]["content"]

    # Export to JSONL file
    out_file = tmp_path / "dataset.jsonl"
    count = exporter.export_to_jsonl(out_file)
    assert count >= 1
    assert out_file.exists()

    line = out_file.read_text(encoding="utf-8").strip().splitlines()[0]
    parsed = json.loads(line)
    assert "messages" in parsed


def test_api_distillation_export_endpoint(tmp_path: Path) -> None:
    client = TestClient(app)
    # Ensure there's at least one run in default store
    task = TaskSpec(
        title="Distill API test task",
        description="Run to be distilled via API",
        repository=str(tmp_path),
        dry_run=True,
    )
    run = AgentRun(task, build_default_registry(), ToolPolicy(), store=get_default_store())
    run.execute()

    resp = client.post("/api/v1/distillation/export?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_records"] >= 1
    assert "records" in data
