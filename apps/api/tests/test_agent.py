from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_run_completes_with_evidence() -> None:
    response = client.post(
        "/api/v1/runs",
        json={
            "task": {
                "title": "Add a feature",
                "description": "Implement a safe engineering change.",
                "repository": "example/repo",
                "constraints": ["keep it bounded"],
            }
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert len(body["verification"]) == 2
