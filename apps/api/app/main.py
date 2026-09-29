from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel
from .change_analysis import analyze_diff
from .domain import TaskSpec
from .policy import ToolPolicy
from .runner import AgentRun
from .tools import build_default_registry

app = FastAPI(title="Agentic Software Engineer", version="0.5.0", description="A guarded, auditable agentic software-engineering control plane.")
_registry = build_default_registry()
_policy = ToolPolicy()

class RunRequest(BaseModel):
    task: TaskSpec
class DiffRequest(BaseModel):
    diff: str

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status":"ok","service":"agentic-software-engineer-api","version":"0.5.0"}

@app.post("/api/v1/runs")
def create_run(request: RunRequest) -> dict[str, object]:
    return AgentRun(request.task, _registry, _policy).execute()

@app.post("/api/v1/analyze-diff")
def analyze(request: DiffRequest) -> dict[str, object]:
    result=analyze_diff(request.diff)
    return {"risk":result.risk,"total_additions":result.total_additions,"total_deletions":result.total_deletions,"files":[item.__dict__ for item in result.files]}
