from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .change_analysis import analyze_diff
from .domain import TaskSpec
from .llm import build_advisor
from .policy import ToolPolicy
from .providers import PlanRequest
from .runner import AgentRun
from .security import SecurityHeadersMiddleware, allowed_origins
from .tools import build_default_registry

app=FastAPI(title="Agentic Software Engineer",version="0.6.0",description="A guarded, auditable agentic software-engineering control plane.")
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=allowed_origins(),allow_methods=["GET","POST"],allow_headers=["*"])
_registry=build_default_registry()
_policy=ToolPolicy()

class RunRequest(BaseModel):
    task: TaskSpec
class DiffRequest(BaseModel):
    diff: str
class AdvisoryRequest(BaseModel):
    task: str
    repository_context: str = ""

@app.get("/api/health")
def health()->dict[str,str]:
    return {"status":"ok","service":"agentic-software-engineer-api","version":"0.6.0"}

@app.post("/api/v1/runs")
def create_run(request:RunRequest)->dict[str,object]:
    return AgentRun(request.task,_registry,_policy).execute()

@app.post("/api/v1/analyze-diff")
def analyze(request:DiffRequest)->dict[str,object]:
    result=analyze_diff(request.diff)
    return {"risk":result.risk,"total_additions":result.total_additions,"total_deletions":result.total_deletions,"files":[item.__dict__ for item in result.files]}

@app.post("/api/v1/advisory")
def advisory(request:AdvisoryRequest)->dict[str,str]:
    provider,name=build_advisor()
    try:
        text=provider.plan(PlanRequest(request.task,request.repository_context))
        return {"provider":name,"advisory":text}
    except Exception:
        fallback=build_advisor()[0]
        return {"provider":"deterministic","advisory":fallback.plan(PlanRequest(request.task,request.repository_context))}
