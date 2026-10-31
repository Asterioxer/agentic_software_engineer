from __future__ import annotations

import uuid
from typing import Any

from .domain import (
    EvidenceRecord,
    FailureCategory,
    FailureDiagnosis,
    RunCheckpoint,
    RunEvent,
    RunStatus,
    StepStatus,
    TaskSpec,
    ToolCall,
    VerificationResult,
)
from .planner import plan_with_repository
from .policy import ToolPolicy
from .reflection import classify_failure, reflect
from .store import RunStore, get_default_store
from .tools import ToolRegistry


class AgentRun:
    """Resilient, auditable control-plane runner with persistent checkpoint recovery."""

    def __init__(
        self,
        task: TaskSpec,
        registry: ToolRegistry,
        policy: ToolPolicy,
        run_id: str | None = None,
        store: RunStore | None = None,
        existing_checkpoint: RunCheckpoint | None = None,
    ) -> None:
        self.task = task
        self.registry = registry
        self.policy = policy
        self.run_id = run_id or (
            existing_checkpoint.run_id if existing_checkpoint else uuid.uuid4().hex[:12]
        )
        self.store = store or get_default_store()
        self.events: list[RunEvent] = (
            list(existing_checkpoint.events) if existing_checkpoint else []
        )
        self.tool_results: list[dict[str, Any]] = (
            list(existing_checkpoint.tool_results) if existing_checkpoint else []
        )
        self.evidence_records: list[EvidenceRecord] = (
            list(existing_checkpoint.evidence_records) if existing_checkpoint else []
        )
        self.retry_count = existing_checkpoint.retry_count if existing_checkpoint else 0
        self.max_retries = task.max_retries
        self.checkpoint = existing_checkpoint or RunCheckpoint(
            run_id=self.run_id,
            task=task,
            status=RunStatus.INTAKE,
            max_retries=self.max_retries,
        )

    def _emit(self, status: RunStatus, message: str) -> None:
        event = RunEvent(sequence=len(self.events) + 1, status=status, message=message)
        self.events.append(event)
        self.checkpoint.events = list(self.events)
        self.checkpoint.status = status
        self.store.append_event(self.run_id, event)

    def _save_checkpoint(self) -> None:
        self.checkpoint.events = list(self.events)
        self.checkpoint.tool_results = list(self.tool_results)
        self.checkpoint.evidence_records = list(self.evidence_records)
        self.store.save_checkpoint(self.checkpoint)

    def execute(self, auto_approved: bool = False) -> dict[str, object]:
        if not self.events:
            self._emit(RunStatus.INTAKE, "Task accepted.")
            self._save_checkpoint()

        # Step 1: Planning (or restoring existing plan)
        if not self.checkpoint.plan:
            try:
                plan, repository = plan_with_repository(self.task)
                self.checkpoint.plan = plan
                self.checkpoint.repository_summary = repository
            except ValueError as exc:
                diagnosis = classify_failure(str(exc))
                self.checkpoint.failure_diagnosis = diagnosis
                self._emit(RunStatus.FAILED, f"Repository inspection failed: {exc}")
                self._save_checkpoint()
                return self._build_response(RunStatus.FAILED)
            self._emit(RunStatus.PLANNING, f"Built context-aware plan with {len(plan)} steps.")
            self._save_checkpoint()
        else:
            plan = self.checkpoint.plan
            repository = self.checkpoint.repository_summary

        self._emit(RunStatus.EXECUTING, "Executing declared tools.")
        self._save_checkpoint()

        # Step 2: Step-by-step execution from current checkpoint index
        for idx in range(self.checkpoint.current_step_index, len(plan)):
            step = plan[idx]
            self.checkpoint.current_step_index = idx

            # Skip already completed steps (for safe checkpoint resumption)
            if step.status == StepStatus.COMPLETED:
                continue

            if not step.tool:
                step.status = StepStatus.COMPLETED
                self._save_checkpoint()
                continue

            # Approval check for non-dry-run mutations
            if step.requires_approval and not auto_approved and not self.task.auto_approve:
                self._emit(
                    RunStatus.AWAITING_APPROVAL,
                    f"Action '{step.id}' requires explicit operator approval before applying mutations.",
                )
                self._save_checkpoint()
                return self._build_response(RunStatus.AWAITING_APPROVAL)

            # Tool call policy authorization
            tool_args = dict(step.inputs)
            if "repository" not in tool_args:
                tool_args["repository"] = self.task.repository
            call = ToolCall(tool=step.tool, arguments=tool_args)
            decision = self.policy.authorize(call)

            if not decision.allowed:
                diagnosis = FailureDiagnosis(
                    category=FailureCategory.POLICY_VIOLATION,
                    message=decision.reason,
                    recoverable=False,
                    suggested_recovery="Terminate run: requested tool is not allowlisted.",
                )
                self.checkpoint.failure_diagnosis = diagnosis
                step.status = StepStatus.FAILED
                step.error = decision.reason
                self._emit(RunStatus.FAILED, decision.reason)
                self._save_checkpoint()
                return self._build_response(RunStatus.FAILED)

            # Execute tool with bounded error handling and retries
            step_passed = False
            while not step_passed and self.retry_count <= self.max_retries:
                try:
                    step.status = StepStatus.RUNNING
                    result, record = self.registry.execute_guarded(step.tool, call.arguments)
                    self.tool_results.append({"tool": step.tool, "result": result})
                    self.evidence_records.append(record)
                    self.store.append_evidence(self.run_id, record)
                    step.output = result

                    # Verify step result
                    if result.get("exit_code") not in (0, None) and not result.get("applied", True):
                        error_detail = result.get("stderr") or result.get(
                            "detail", "Non-zero exit code"
                        )
                        raise RuntimeError(error_detail)

                    step.status = StepStatus.COMPLETED
                    step_passed = True
                except (OSError, ValueError, KeyError, RuntimeError) as exc:
                    diagnosis = classify_failure(str(exc), step_output=step.output)
                    self.checkpoint.failure_diagnosis = diagnosis
                    step.error = str(exc)

                    if diagnosis.recoverable and self.retry_count < self.max_retries:
                        self.retry_count += 1
                        self.checkpoint.retry_count = self.retry_count
                        self._emit(
                            RunStatus.REFLECTING,
                            f"Step '{step.id}' failed ({diagnosis.category.value}). Retrying ({self.retry_count}/{self.max_retries}): {diagnosis.suggested_recovery}",
                        )
                        self._save_checkpoint()
                    else:
                        step.status = StepStatus.FAILED
                        self._emit(RunStatus.FAILED, f"{step.tool} failed: {exc}")
                        self._save_checkpoint()
                        return self._build_response(RunStatus.FAILED)

            self._save_checkpoint()

        # Step 3: Independent Verification
        self._emit(RunStatus.VERIFYING, "Running independent deterministic checks.")
        results = [
            VerificationResult(check="plan_exists", passed=bool(plan), detail="Plan is non-empty."),
            VerificationResult(
                check="repository_context",
                passed=self.task.repository is None or repository is not None,
                detail="Repository context was inspected when requested.",
            ),
            VerificationResult(
                check="tool_allowlist",
                passed=all(
                    step.tool is None or self.policy.authorize(ToolCall(tool=step.tool)).allowed
                    for step in plan
                ),
                detail="Declared tools are policy-approved.",
            ),
        ]

        verification_tool = next(
            (item["result"] for item in self.tool_results if item["tool"] == "verification.run"),
            None,
        )
        if isinstance(verification_tool, dict):
            results.extend(
                VerificationResult(**item)
                for item in verification_tool.get("checks", [])
                if isinstance(item, dict)
            )

        self.checkpoint.verification = results

        if not all(result.passed for result in results):
            diagnosis = classify_failure("Verification failed", verification_results=results)
            self.checkpoint.failure_diagnosis = diagnosis
            reflection = reflect(results, retry_budget=self.max_retries - self.retry_count)
            self._emit(RunStatus.FAILED, f"Verification failed. {reflection.diagnosis}")
            self._save_checkpoint()
            return self._build_response(RunStatus.FAILED)

        # Step 4: Reflection & Completion
        self._emit(RunStatus.REFLECTING, "Summarizing execution evidence.")
        self._emit(RunStatus.COMPLETED, "Run completed with verification evidence.")
        self._save_checkpoint()
        return self._build_response(RunStatus.COMPLETED)

    def _build_response(self, status: RunStatus) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": status.value,
            "task": self.task.model_dump(),
            "plan": [s.model_dump() for s in self.checkpoint.plan],
            "repository": self.checkpoint.repository_summary,
            "tool_results": self.tool_results,
            "verification": [v.model_dump() for v in self.checkpoint.verification],
            "events": [e.model_dump() for e in self.events],
            "evidence_records": [r.model_dump() for r in self.evidence_records],
            "failure_diagnosis": self.checkpoint.failure_diagnosis.model_dump()
            if self.checkpoint.failure_diagnosis
            else None,
            "checkpoint": self.checkpoint.model_dump(),
        }


def resume_run(
    run_id: str,
    approved: bool = False,
    registry: ToolRegistry | None = None,
    policy: ToolPolicy | None = None,
    store: RunStore | None = None,
) -> dict[str, object]:
    """Resume an existing run from its stored checkpoint, honoring operator approval."""
    effective_store = store or get_default_store()
    checkpoint = effective_store.get_checkpoint(run_id)
    if not checkpoint:
        raise ValueError(f"Run '{run_id}' not found in checkpoint store.")

    from .policy import ToolPolicy
    from .tools import build_default_registry

    effective_registry = registry or build_default_registry()
    effective_policy = policy or ToolPolicy()

    runner = AgentRun(
        task=checkpoint.task,
        registry=effective_registry,
        policy=effective_policy,
        run_id=checkpoint.run_id,
        store=effective_store,
        existing_checkpoint=checkpoint,
    )
    return runner.execute(auto_approved=approved)
