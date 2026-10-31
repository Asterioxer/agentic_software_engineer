from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .change_analysis import analyze_diff
from .domain import TaskSpec
from .llm import build_advisor
from .policy import ToolPolicy
from .providers import DeterministicProvider, PlanRequest
from .runner import AgentRun, resume_run
from .security import SecurityHeadersMiddleware, allowed_origins
from .store import get_default_store
from .tools import build_default_registry

app = FastAPI(
    title="Agentic Software Engineer",
    version="0.6.0",
    description="A guarded, auditable agentic software-engineering control plane.",
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
_registry = build_default_registry()
_policy = ToolPolicy()
_store = get_default_store()


class RunRequest(BaseModel):
    task: TaskSpec


class ResumeRequest(BaseModel):
    approved: bool = Field(default=True)


class DiffRequest(BaseModel):
    diff: str


class AdvisoryRequest(BaseModel):
    task: str
    repository_context: str = ""


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentic-software-engineer-api", "version": "0.6.0"}


@app.post("/api/v1/runs")
def create_run(request: RunRequest) -> dict[str, object]:
    return AgentRun(request.task, _registry, _policy, store=_store).execute()


@app.get("/api/v1/runs")
def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    return _store.list_runs(limit=limit)


@app.get("/api/v1/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    checkpoint = _store.get_checkpoint(run_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return checkpoint.model_dump()


@app.post("/api/v1/runs/{run_id}/resume")
def resume(run_id: str, request: ResumeRequest) -> dict[str, object]:
    try:
        return resume_run(
            run_id=run_id,
            approved=request.approved,
            registry=_registry,
            policy=_policy,
            store=_store,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/v1/analyze-diff")
def analyze(request: DiffRequest) -> dict[str, object]:
    result = analyze_diff(request.diff)
    return {
        "risk": result.risk,
        "total_additions": result.total_additions,
        "total_deletions": result.total_deletions,
        "files": [item.__dict__ for item in result.files],
    }


@app.post("/api/v1/advisory")
def advisory(request: AdvisoryRequest) -> dict[str, str]:
    provider, name = build_advisor()
    try:
        text = provider.plan(PlanRequest(request.task, request.repository_context))
        return {"provider": name, "advisory": text}
    except Exception:  # noqa: BLE001
        fallback = DeterministicProvider()
        return {
            "provider": "deterministic",
            "advisory": fallback.plan(PlanRequest(request.task, request.repository_context)),
        }
