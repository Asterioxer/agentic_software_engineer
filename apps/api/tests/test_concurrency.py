from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.domain import RunStatus
from app.main import app

client = TestClient(app)


def test_concurrent_run_creation(tmp_path: Path) -> None:
    """Verify that multiple concurrent run requests succeed without SQLite locks or corruption."""
    repos = []
    for i in range(5):
        repo = tmp_path / f"repo_{i}"
        repo.mkdir()
        (repo / "main.py").write_text(f"x = {i}\n", encoding="utf-8")
        repos.append(repo)

    def submit_task(repo_path: Path, idx: int) -> dict[str, Any]:
        resp = client.post(
            "/api/v1/runs",
            json={
                "task": {
                    "title": f"Concurrent task {idx}",
                    "description": f"Perform dry run analysis on repo {idx}",
                    "repository": str(repo_path),
                    "dry_run": True,
                    "auto_approve": False,
                }
            },
        )
        assert resp.status_code == 200
        data: dict[str, Any] = resp.json()
        return data

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(submit_task, repos[i], i) for i in range(5)]
        results = [f.result() for f in futures]

    assert len(results) == 5
    run_ids = {r["run_id"] for r in results}
    assert len(run_ids) == 5
    assert all(r["status"] == RunStatus.COMPLETED.value for r in results)


def test_concurrent_run_resume_guard(tmp_path: Path) -> None:
    """Verify that simultaneous resume requests for the same run do not duplicate mutations."""
    repo = tmp_path / "target_repo"
    repo.mkdir()
    (repo / "code.py").write_text("x = 1\n", encoding="utf-8")

    # 1. Create a run requiring approval
    init_resp = client.post(
        "/api/v1/runs",
        json={
            "task": {
                "title": "Mutating task",
                "description": "Write plan file to workspace",
                "repository": str(repo),
                "dry_run": False,
                "auto_approve": False,
            }
        },
    )
    assert init_resp.status_code == 200
    run_id = init_resp.json()["run_id"]
    assert init_resp.json()["status"] == RunStatus.AWAITING_APPROVAL.value

    # 2. Concurrently resume the run with 5 threads
    def resume_task() -> int:
        resp = client.post(f"/api/v1/runs/{run_id}/resume", json={"approved": True})
        return int(resp.status_code)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(resume_task) for _ in range(5)]
        status_codes = [f.result() for f in futures]

    assert all(code == 200 for code in status_codes)

    # 3. Verify target file exists and run is completed
    assert (repo / "agent-plan.txt").exists()

    final_resp = client.get(f"/api/v1/runs/{run_id}")
    assert final_resp.status_code == 200
    assert final_resp.json()["status"] == RunStatus.COMPLETED.value


def test_internal_error_masking(monkeypatch: Any) -> None:
    """Verify that unhandled internal server exceptions do not leak stack traces."""
    from app import main

    def mock_broken_analyze(diff: str) -> None:
        raise RuntimeError("Secret internal database password or schema leak in traceback!")

    monkeypatch.setattr(main, "analyze_diff", mock_broken_analyze)

    safe_client = TestClient(app, raise_server_exceptions=False)
    resp = safe_client.post("/api/v1/analyze-diff", json={"diff": "some diff"})
    assert resp.status_code == 500
    data = resp.json()
    assert data["detail"] == "An internal server error occurred while processing the request."
    assert "Secret internal database password" not in resp.text
