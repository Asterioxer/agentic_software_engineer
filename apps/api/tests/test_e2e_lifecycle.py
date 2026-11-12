from pathlib import Path

from fastapi.testclient import TestClient

from app.domain import RunStatus
from app.main import app

client = TestClient(app)


def test_e2e_complete_agent_lifecycle(tmp_path: Path) -> None:
    # 1. Setup mock repo
    repo = tmp_path / "target_repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "README.md").write_text("# Calculator App\n")

    # 2. Submit initial dry-run task
    resp = client.post(
        "/api/v1/runs",
        json={
            "task": {
                "title": "Add subtract function",
                "description": "Implement subtract(a, b) in calc.py with independent checks.",
                "repository": str(repo),
                "dry_run": True,
                "auto_approve": False,
            }
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == RunStatus.COMPLETED.value
    data["run_id"]
    assert len(data["plan"]) >= 4
    assert data["repository"]["file_count"] == 2
    assert "python" in data["repository"]["languages"]

    # Verify audit timeline and evidence records
    assert len(data["events"]) >= 5
    assert len(data["evidence_records"]) >= 2
    assert any(e["status"] == "planning" for e in data["events"])
    assert any(e["status"] == "verifying" for e in data["events"])
    assert any(e["status"] == "completed" for e in data["events"])

    # 3. Submit real mutation task requiring operator approval
    mutate_resp = client.post(
        "/api/v1/runs",
        json={
            "task": {
                "title": "Deploy production patch",
                "description": "Apply actual changes to workspace",
                "repository": str(repo),
                "dry_run": False,
                "auto_approve": False,
            }
        },
    )
    assert mutate_resp.status_code == 200
    mutate_data = mutate_resp.json()
    assert mutate_data["status"] == RunStatus.AWAITING_APPROVAL.value
    pause_run_id = mutate_data["run_id"]

    # 4. Resume paused run with explicit operator approval
    resume_resp = client.post(f"/api/v1/runs/{pause_run_id}/resume", json={"approved": True})
    assert resume_resp.status_code == 200
    resumed_data = resume_resp.json()
    assert resumed_data["status"] == RunStatus.COMPLETED.value

    # Verify file was written to disk
    assert (repo / "agent-plan.txt").exists()

    # 5. Check evaluation runner endpoint
    eval_resp = client.post("/api/v1/evaluations/run")
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["total_scenarios"] == 25
    assert eval_data["pass_rate"] == 1.0
    assert eval_data["policy_adherence_rate"] == 1.0
    assert eval_data["truthfulness_rate"] == 1.0

    # 6. Check latest evaluation report endpoint
    latest_resp = client.get("/api/v1/evaluations/latest")
    assert latest_resp.status_code == 200
    assert latest_resp.json()["total_scenarios"] == 25
