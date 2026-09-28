from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .domain import TaskSpec
from .policy import ToolPolicy
from .runner import AgentRun
from .tools import build_default_registry

app = FastAPI(
    title="Agentic Software Engineer",
    version="0.1.0",
    description="A guarded, auditable agentic software-engineering control plane.",
)

_registry = build_default_registry()
_policy = ToolPolicy()


class RunRequest(BaseModel):
    task: TaskSpec


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentic-software-engineer-api"}


@app.post("/api/v1/runs")
def create_run(request: RunRequest) -> dict[str, object]:
    return AgentRun(request.task, _registry, _policy).execute()
