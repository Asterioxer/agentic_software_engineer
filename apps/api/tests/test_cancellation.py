from __future__ import annotations

import argparse
from pathlib import Path

from fastapi.testclient import TestClient

from app.cli import cmd_cancel
from app.domain import FailureCategory, RunStatus, TaskSpec
from app.main import app
from app.policy import ToolPolicy
from app.runner import AgentRun
from app.store import RunStore
from app.tools import build_default_registry

client = TestClient(app)


def test_agent_run_direct_cancellation(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_cancel.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Cancel me",
        description="Should not finish",
        repository=str(tmp_path),
        dry_run=True,
    )

    run = AgentRun(task, registry, policy, store=store)
    res = run.cancel(reason="Aborted by user test")
    assert res["status"] == RunStatus.FAILED.value

    checkpoint = store.get_checkpoint(run.run_id)
    assert checkpoint is not None
    assert checkpoint.cancellation_requested is True
    assert checkpoint.failure_diagnosis is not None
    assert checkpoint.failure_diagnosis.category == FailureCategory.CANCELLED

    # If run.execute() is called after cancellation, it immediately halts
    exec_res = run.execute()
    assert exec_res["status"] == RunStatus.FAILED.value


def test_api_cancel_endpoint(tmp_path: Path) -> None:
    create_resp = client.post(
        "/api/v1/runs",
        json={
            "task": {
                "title": "Awaiting approval run",
                "description": "Mutating task",
                "repository": str(tmp_path),
                "dry_run": False,
                "auto_approve": False,
            }
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["run_id"]
    assert create_resp.json()["status"] == "awaiting_approval"

    # Cancel via API
    cancel_resp = client.post(
        f"/api/v1/runs/{run_id}/cancel",
        json={"reason": "Testing API cancellation"},
    )
    assert cancel_resp.status_code == 200
    data = cancel_resp.json()
    assert data["cancelled"] is True
    assert data["run_id"] == run_id

    # Verify run detail reports failure
    detail_resp = client.get(f"/api/v1/runs/{run_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["status"] == "failed"
    assert detail["cancellation_requested"] is True


def test_api_cancel_nonexistent_run() -> None:
    resp = client.post("/api/v1/runs/nonexistent_12345/cancel")
    assert resp.status_code == 404


def test_websocket_cancel_action(tmp_path: Path) -> None:
    create_resp = client.post(
        "/api/v1/runs",
        json={
            "task": {
                "title": "WS Cancel run",
                "description": "Mutating task",
                "repository": str(tmp_path),
                "dry_run": False,
                "auto_approve": False,
            }
        },
    )
    assert create_resp.status_code == 200
    run_id = create_resp.json()["run_id"]

    with client.websocket_connect(f"/api/v1/ws/runs/{run_id}") as ws:
        ws.send_json({"action": "cancel", "reason": "Operator abort via WS"})
        action_resp = None
        for _ in range(15):
            msg = ws.receive_json()
            if msg.get("event_type") == "action_result":
                action_resp = msg
                break
        assert action_resp is not None
        assert action_resp.get("action") == "cancel"
        assert action_resp.get("status") == "cancelled"


def test_cli_cancel_command(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test_cli_cancel.db")
    store = RunStore(db_path)
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="CLI cancel run",
        description="Pending task",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=False,
    )
    run = AgentRun(task, registry, policy, store=store)
    run.execute()

    args = argparse.Namespace(
        run_id=run.run_id,
        reason="CLI test operator abort",
        db=db_path,
    )
    code = cmd_cancel(args)
    assert code == 0

    checkpoint = store.get_checkpoint(run.run_id)
    assert checkpoint is not None
    assert checkpoint.cancellation_requested is True
    assert checkpoint.status == RunStatus.FAILED
