from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_api_list_and_get_runs(tmp_path: Path) -> None:
    (tmp_path / "hello.py").write_text("print('hello')", encoding="utf-8")
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


def test_api_critic_review_diff_endpoint() -> None:
    diff = """--- a/src/safe.py
+++ b/src/safe.py
@@ -1,1 +1,2 @@
 x = 1
+token = 'sk_live_1234567890abcdef'
"""
    resp = client.post("/api/v1/critic/review-diff", json={"diff": diff})
    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is False
    assert len(data["findings"]) >= 1
    assert "Review rejected" in data["summary"]


def test_api_critic_review_workspace_endpoint(tmp_path: Path) -> None:
    file = tmp_path / "main.py"
    file.write_text("def run(): return 42\n", encoding="utf-8")

    resp = client.post(
        "/api/v1/critic/review-workspace",
        json={"repository": str(tmp_path), "files": ["main.py"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approved"] is True
    assert data["risk_score"] == 0.0


def test_api_deliberate_endpoint(tmp_path: Path) -> None:
    resp = client.post(
        "/api/v1/deliberate",
        json={
            "task": {
                "title": "Build user auth subsystem",
                "description": "Design modular authentication tokens",
                "repository": str(tmp_path),
            }
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consensus_reached"] is True
    assert "app/auth.py" in data["target_files"]
    assert len(data["steps"]) >= 4
    assert data["critic_approved"] is True


def test_api_blast_radius_endpoint(tmp_path: Path) -> None:
    (tmp_path / "core.py").write_text("def core_fn(): pass\n", encoding="utf-8")
    (tmp_path / "service.py").write_text(
        "import core\ndef svc(): core.core_fn()\n", encoding="utf-8"
    )

    resp = client.post(
        "/api/v1/repository/blast-radius",
        json={"repository": str(tmp_path), "target_file": "core.py"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_file"] == "core.py"
    assert "service.py" in data["direct_dependents"]
    assert data["total_impacted_files"] >= 1
