from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncGenerator
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .change_analysis import analyze_diff
from .codegraph import CodeGraph
from .critic import review_diff, review_workspace
from .deliberation import DeliberationCouncil
from .distillation import DatasetExporter
from .domain import RunStatus, TaskSpec
from .evaluation import IndependentEvaluator
from .integrations import (
    format_github_pr_comment,
    parse_github_event,
    verify_github_signature,
)
from .llm import build_advisor
from .policy import ToolPolicy
from .providers import DeterministicProvider, PlanRequest
from .runner import AgentRun, resume_run
from .security import SecurityHeadersMiddleware, allowed_origins
from .store import get_default_store
from .telemetry import RunEvent, get_event_bus
from .tools import build_default_registry

logger = logging.getLogger("agentic_software_engineer")

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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    logger.exception(
        "Unhandled server exception on %s %s: %s", request.method, request.url.path, exc
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred while processing the request."},
    )


_registry = build_default_registry()
_policy = ToolPolicy()
_store = get_default_store()


class RunRequest(BaseModel):
    task: TaskSpec


class ResumeRequest(BaseModel):
    approved: bool = Field(default=False)
    plan_fingerprint: str | None = Field(default=None)


class CancelRequest(BaseModel):
    reason: str = Field(default="Operator requested cancellation", max_length=200)


class DiffRequest(BaseModel):
    diff: str


class AdvisoryRequest(BaseModel):
    task: str
    repository_context: str = ""


class CriticDiffRequest(BaseModel):
    diff: str = Field(min_length=1, max_length=200_000)


class CriticWorkspaceRequest(BaseModel):
    repository: str = Field(min_length=1, max_length=500)
    files: list[str] = Field(default_factory=list, max_length=50)


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
    data = checkpoint.model_dump()
    data["operations"] = [op.model_dump() for op in _store.list_operations_for_run(run_id)]
    return data


@app.get("/api/v1/runs/{run_id}/stream")
async def stream_run_events(run_id: str) -> StreamingResponse:
    checkpoint = _store.get_checkpoint(run_id)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")

    bus = get_event_bus()

    async def event_generator() -> AsyncGenerator[str, None]:
        # 1. Replay past events
        for ev in bus.get_history(run_id):
            yield ev.to_sse()

        # 2. If already in terminal status, complete stream
        terminal_statuses = (
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.AWAITING_APPROVAL.value,
            RunStatus.RECONCILIATION_REQUIRED.value,
        )
        if checkpoint.status.value in terminal_statuses:
            return

        # 3. Stream live events
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue(maxsize=100)
        bus.register_queue(run_id, queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10.0)
                    if event is None:
                        break
                    yield event.to_sse()
                    if event.payload.get("status") in terminal_statuses:
                        break
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            bus.unregister_queue(run_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.websocket("/api/v1/ws/runs/{run_id}")
async def websocket_run_endpoint(websocket: WebSocket, run_id: str) -> None:
    checkpoint = _store.get_checkpoint(run_id)
    if not checkpoint:
        await websocket.close(code=4004, reason=f"Run '{run_id}' not found.")
        return

    await websocket.accept()
    bus = get_event_bus()

    # 1. Replay historical events
    for ev in bus.get_history(run_id):
        await websocket.send_text(ev.to_json())

    # 2. Live subscription queue
    queue: asyncio.Queue[RunEvent | None] = asyncio.Queue(maxsize=200)
    bus.register_queue(run_id, queue)

    async def sender() -> None:
        try:
            while True:
                ev = await queue.get()
                if ev is None:
                    await websocket.send_json({"event_type": "stream_closed", "run_id": run_id})
                    break
                await websocket.send_text(ev.to_json())
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass

    sender_task = asyncio.create_task(sender())

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            if action == "ping":
                await websocket.send_json({"event_type": "pong", "timestamp": time.time()})
            elif action == "approve":
                res = resume_run(
                    run_id=run_id,
                    approved=True,
                    registry=_registry,
                    policy=_policy,
                    store=_store,
                )
                await websocket.send_json(
                    {
                        "event_type": "action_result",
                        "action": "approve",
                        "status": res.get("status"),
                    }
                )
            elif action == "cancel":
                checkpoint = _store.cancel_run(run_id, reason="Cancelled via WebSocket")
                bus.publish(
                    run_id=run_id,
                    event_type="status:failed",
                    payload={"status": "failed", "message": "Cancelled via WebSocket"},
                )
                await websocket.send_json(
                    {"event_type": "action_result", "action": "cancel", "status": "cancelled"}
                )
                break
            elif action == "steer":
                guidance = str(data.get("guidance", "")).strip()
                if guidance:
                    bus.publish(
                        run_id=run_id,
                        event_type="operator:guidance",
                        payload={"guidance": guidance, "timestamp": time.time()},
                    )
                    await websocket.send_json(
                        {
                            "event_type": "action_result",
                            "action": "steer",
                            "status": "guidance_recorded",
                            "guidance": guidance,
                        }
                    )
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        bus.unregister_queue(run_id, queue)


@app.post("/api/v1/runs/{run_id}/resume")
def resume(run_id: str, request: ResumeRequest) -> dict[str, object]:
    try:
        return resume_run(
            run_id=run_id,
            approved=request.approved,
            registry=_registry,
            policy=_policy,
            store=_store,
            expected_fingerprint=request.plan_fingerprint,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/runs/{run_id}/cancel")
def cancel_run_endpoint(run_id: str, request: CancelRequest | None = None) -> dict[str, Any]:
    reason = request.reason if request else "Operator requested cancellation"
    checkpoint = _store.cancel_run(run_id, reason=reason)
    if not checkpoint:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    bus = get_event_bus()
    bus.publish(
        run_id=run_id,
        event_type="status:failed",
        payload={"status": "failed", "message": f"Cancelled: {reason}"},
    )
    return {"run_id": run_id, "status": "failed", "cancelled": True, "reason": reason}


@app.post("/api/v1/analyze-diff")
def analyze(request: DiffRequest) -> dict[str, object]:
    result = analyze_diff(request.diff)
    return {
        "risk": result.risk,
        "total_additions": result.total_additions,
        "total_deletions": result.total_deletions,
        "files": [item.__dict__ for item in result.files],
    }


@app.post("/api/v1/critic/review-diff")
def critic_review_diff(request: CriticDiffRequest) -> dict[str, Any]:
    review = review_diff(request.diff)
    return review.to_dict()


@app.post("/api/v1/critic/review-workspace")
def critic_review_workspace(request: CriticWorkspaceRequest) -> dict[str, Any]:
    review = review_workspace(request.repository, request.files)
    return review.to_dict()


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


@app.post("/api/v1/evaluations/run")
def run_evaluations() -> dict[str, Any]:
    evaluator = IndependentEvaluator()
    report = evaluator.run_all()
    result: dict[str, Any] = asdict(report)
    return result


@app.get("/api/v1/evaluations/latest")
def get_latest_evaluation() -> dict[str, Any]:
    report_file = Path("evaluation_reports/evaluation_report.json")
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="No evaluation report generated yet.")
    data: dict[str, Any] = json.loads(report_file.read_text(encoding="utf-8"))
    return data


@app.post("/api/v1/deliberate")
def deliberate(request: RunRequest) -> dict[str, Any]:
    council = DeliberationCouncil()
    res = council.deliberate(request.task, repo_root=request.task.repository)
    return {
        "task_title": res.task_title,
        "consensus_reached": res.consensus_reached,
        "iterations_used": res.iterations_used,
        "summary": res.summary,
        "target_files": list(res.architect_proposal.target_files),
        "steps": list(res.architect_proposal.proposed_steps),
        "risk_score": res.critic_verdict.risk_score,
        "critic_approved": res.critic_verdict.approved,
    }


@app.get("/api/v1/evaluations/swe-bench/latest")
def get_latest_swe_bench() -> dict[str, Any]:
    report_file = Path("evaluation_reports/swe_bench_report.json")
    if not report_file.exists():
        raise HTTPException(status_code=404, detail="No SWE-bench evaluation report generated yet.")
    data: dict[str, Any] = json.loads(report_file.read_text(encoding="utf-8"))
    return data


@app.post("/api/v1/integrations/github/webhook")
async def github_webhook(request: Request) -> dict[str, Any]:
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    sig_header = request.headers.get("X-Hub-Signature-256")
    body_bytes = await request.body()

    if secret and not verify_github_signature(body_bytes, sig_header, secret):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature.")

    event_type = request.headers.get("X-GitHub-Event", "issues")
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.") from exc

    task = parse_github_event(event_type, payload)
    if not task:
        return {"status": "ignored", "event": event_type, "reason": "No actionable trigger"}

    run = AgentRun(task, _registry, _policy, store=_store)
    result = run.execute()
    comment = format_github_pr_comment(result)

    return {
        "status": "processed",
        "event": event_type,
        "run_id": run.run_id,
        "run_status": result.get("status"),
        "github_comment": comment,
    }


@app.post("/api/v1/distillation/export")
def export_dataset(limit: int = 1000) -> dict[str, Any]:
    exporter = DatasetExporter(_store)
    records = exporter.extract_training_records(limit=limit)
    return {"total_records": len(records), "records": records}


class BlastRadiusRequest(BaseModel):
    repository: str
    target_file: str


@app.post("/api/v1/repository/blast-radius")
def calculate_blast_radius(request: BlastRadiusRequest) -> dict[str, Any]:
    repo_path = Path(request.repository).resolve()
    if not repo_path.is_dir():
        raise HTTPException(status_code=400, detail="Repository path does not exist.")
    graph = CodeGraph(repo_path)
    radius = graph.get_blast_radius(request.target_file)
    return {
        "target_file": radius.target_file,
        "direct_dependents": radius.direct_dependents,
        "transitive_dependents": radius.transitive_dependents,
        "affected_tests": radius.affected_tests,
        "impact_level": radius.impact_level,
        "total_impacted_files": radius.total_impacted_files,
    }
