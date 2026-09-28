from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)
def test_run_completes_with_repository_context(tmp_path:Path)->None:
    (tmp_path/"main.py").write_text("print('hello')");(tmp_path/"README.md").write_text("# repo")
    r=client.post("/api/v1/runs",json={"task":{"title":"Add a feature","description":"Implement a safe engineering change.","repository":str(tmp_path)}})
    assert r.status_code==200;body=r.json();assert body["status"]=="completed";assert body["repository"]["file_count"]==2;assert len(body["verification"])==3
