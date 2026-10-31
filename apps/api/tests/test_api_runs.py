from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_api_list_and_get_runs(tmp_path: Path) -> None:
    (tmp_path / "hello.py").write_text("print('hello')")
    create_resp = client.post(
        "/api/v1/runs",
        json={
            "task": {
                "title": "API test run",
                "description": "Verify API lifecycle and store",
                "repository": str(tmp_path),
            }
        },
    )
    assert create_resp.status_code == 200
    body = create_resp.json()
    run_id = body["run_id"]
    assert body["status"] == "completed"

    # GET /api/v1/runs
    list_resp = client.get("/api/v1/runs")
    assert list_resp.status_code == 200
    runs = list_resp.json()
    assert any(r["run_id"] == run_id for r in runs)

    # GET /api/v1/runs/{run_id}
    detail_resp = client.get(f"/api/v1/runs/{run_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["run_id"] == run_id
    assert detail["status"] == "completed"
    assert len(detail["plan"]) > 0


def test_api_resume_endpoint(tmp_path: Path) -> None:
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
    body = create_resp.json()
    assert body["status"] == "awaiting_approval"
    run_id = body["run_id"]

    # Resume with approval
    resume_resp = client.post(f"/api/v1/runs/{run_id}/resume", json={"approved": True})
    assert resume_resp.status_code == 200
    resumed = resume_resp.json()
    assert resumed["status"] == "completed"
