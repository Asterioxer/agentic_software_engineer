from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain import (
    ApprovalRequest,
    EvidenceRecord,
    FailureCategory,
    FailureDiagnosis,
    JournalOperation,
    OperationState,
    PlanStep,
    RunCheckpoint,
    RunEvent,
    RunStatus,
    StepStatus,
    TaskSpec,
    ToolCall,
    VerificationResult,
)
from .execution import WorkspaceAction, WorkspaceExecutor, compute_file_hash
from .planner import plan_with_repository
from .policy import ToolPolicy
from .reflection import classify_failure, reflect
from .self_correction import SelfCorrectionEngine
from .store import RunStore, get_default_store
from .telemetry import get_event_bus
from .tools import ToolRegistry


def compute_plan_fingerprint(plan: list[PlanStep], diff_text: str | None = None) -> str:
    """Compute deterministic cryptographic fingerprint of execution plan and proposed mutations."""
    plan_payload = [
        {
            "id": s.id,
            "tool": s.tool,
            "inputs": s.inputs,
            "depends_on": s.depends_on,
            "preconditions": s.preconditions,
            "postconditions": s.postconditions,
            "requires_approval": s.requires_approval,
        }
        for s in plan
    ]
    raw = json.dumps(plan_payload, sort_keys=True)
    if diff_text:
        raw += f"::diff::{diff_text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_proposed_diff(plan: list[PlanStep], repo_root: str | None = None) -> str:
    """Extract or synthesize the proposed diff text across mutation steps in the plan."""
    diffs: list[str] = []
    for step in plan:
        if step.tool == "workspace.plan" and step.inputs.get("path") and step.inputs.get("content"):
            path = str(step.inputs["path"])
            new_content = str(step.inputs["content"])
            diffs.append(f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n+{new_content}")
        elif step.tool == "workspace.patch" and step.inputs.get("patch"):
            diffs.append(str(step.inputs["patch"]))
    return "\n".join(diffs)


class AgentRun:
    """Resilient, auditable control-plane runner with persistent checkpoint recovery,

    cryptographic approval binding, and operation journaling.
    """

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
        self.correction_engine = SelfCorrectionEngine()

    def _emit(self, status: RunStatus, message: str) -> None:
        event = RunEvent(sequence=len(self.events) + 1, status=status, message=message)
        self.events.append(event)
        self.checkpoint.events = list(self.events)
        self.checkpoint.status = status
        self.store.append_event(self.run_id, event)
        get_event_bus().publish(
            run_id=self.run_id,
            event_type=f"status:{status.value}",
            payload={"sequence": event.sequence, "status": status.value, "message": message},
        )

    def _save_checkpoint(self) -> None:
        self.checkpoint.events = list(self.events)
        self.checkpoint.tool_results = list(self.tool_results)
        self.checkpoint.evidence_records = list(self.evidence_records)
        self.store.save_checkpoint(self.checkpoint)

    def cancel(self, reason: str = "Operator requested cancellation") -> dict[str, object]:
        """Abort execution cleanly upon operator cancellation request."""
        self.checkpoint.cancellation_requested = True
        self._emit(RunStatus.FAILED, f"Execution cancelled: {reason}")
        self.checkpoint.failure_diagnosis = FailureDiagnosis(
            category=FailureCategory.CANCELLED,
            message=reason,
            recoverable=False,
            suggested_recovery="Run was explicitly cancelled by operator.",
        )
        self._save_checkpoint()
        return self._build_response(RunStatus.FAILED)

    def _reconcile_interrupted_operations(self) -> bool:
        """Scan and reconcile any operations that were interrupted mid-flight."""
        interrupted = self.store.mark_interrupted_operations(self.run_id)
        for op in interrupted:
            self._emit(
                RunStatus.REFLECTING,
                f"Interrupted operation {op.operation_id} (step '{op.step_id}') detected. Performing reconciliation...",
            )
            # File mutation reconciliation
            if op.tool == "workspace.plan" and op.precondition_hash and op.postcondition_hash:
                repo_path = self.task.repository or "."
                file_rel = str(op.inputs.get("path", "agent-plan.txt"))
                try:
                    target = (Path(repo_path) / file_rel).resolve()
                    current_hash = compute_file_hash(target)
                except (OSError, ValueError) as exc:
                    self._emit(
                        RunStatus.RECONCILIATION_REQUIRED, f"Failed to check target file: {exc}"
                    )
                    return False

                if current_hash == op.postcondition_hash:
                    self.store.update_operation_state(
                        op.operation_id,
                        OperationState.SUCCEEDED,
                        recovery_status="reconciled_from_postcondition",
                    )
                    self._emit(
                        RunStatus.REFLECTING,
                        f"Operation {op.operation_id} reconciled: disk matches postcondition hash.",
                    )
                elif current_hash == op.precondition_hash:
                    self.store.update_operation_state(
                        op.operation_id,
                        OperationState.PENDING,
                        recovery_status="unapplied_clean_precondition",
                    )
                    self._emit(
                        RunStatus.REFLECTING,
                        f"Operation {op.operation_id} clean: disk matches precondition hash (unapplied).",
                    )
                else:
                    self.store.update_operation_state(
                        op.operation_id,
                        OperationState.RECONCILIATION_REQUIRED,
                        recovery_status="hash_diverged_from_expected",
                    )
                    self._emit(
                        RunStatus.RECONCILIATION_REQUIRED,
                        f"Fatal reconciliation divergence for operation {op.operation_id} on {file_rel}. Manual intervention required.",
                    )
                    return False
        return True

    def _attempt_self_healing_repair(self, failing_results: list[VerificationResult]) -> bool:
        """Attempt to autonomously repair code when a verification check fails."""
        if self.retry_count >= self.max_retries:
            return False

        repo_root = Path(self.task.repository or ".").resolve()
        repaired = False

        for r in failing_results:
            if not r.passed:
                plan = self.correction_engine.generate_corrective_plan(
                    failing_check=r.check,
                    error_detail=r.detail,
                    workspace_root=self.task.repository or ".",
                )
                if plan.is_loop:
                    self._emit(
                        RunStatus.REFLECTING,
                        "Anti-cycling gate: identical repair strategy previously failed. Refusing to loop.",
                    )
                    self.checkpoint.failure_diagnosis = FailureDiagnosis(
                        category=FailureCategory.STRATEGY_LOOP,
                        message="Strategy loop detected: agent attempted the exact same code repair strategy repeatedly.",
                        recoverable=False,
                        suggested_recovery="Review failure logs and supply manual correction.",
                    )
                    return False

                if plan.approved and plan.proposed_code is not None and plan.target_file:
                    target_path = (repo_root / plan.target_file).resolve()
                    self.retry_count += 1
                    self.checkpoint.retry_count = self.retry_count
                    self._emit(
                        RunStatus.REFLECTING,
                        f"Autonomous self-healing attempt {self.retry_count}/{self.max_retries}: repaired {plan.target_file}",
                    )
                    if not self.task.dry_run:
                        target_path.write_text(plan.proposed_code, encoding="utf-8")
                    repaired = True
                    break

        return repaired

    def execute(self, auto_approved: bool = False) -> dict[str, object]:
        # Step -1: Check if run was cancelled before start
        if self.checkpoint.cancellation_requested:
            self._emit(RunStatus.FAILED, "Execution aborted: run was cancelled by operator.")
            self.checkpoint.failure_diagnosis = FailureDiagnosis(
                category=FailureCategory.CANCELLED,
                message="Run was cancelled by operator request.",
                recoverable=False,
                suggested_recovery="Re-dispatch task if desired.",
            )
            self._save_checkpoint()
            return self._build_response(RunStatus.FAILED)

        if not self.events:
            self._emit(RunStatus.INTAKE, "Task accepted.")
            self._save_checkpoint()

        # Step 0: Crash reconciliation check
        if not self._reconcile_interrupted_operations():
            self._save_checkpoint()
            return self._build_response(RunStatus.RECONCILIATION_REQUIRED)

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
            # Check for cancellation before each step
            if self.checkpoint.cancellation_requested:
                self._emit(
                    RunStatus.FAILED,
                    f"Execution aborted at step index {idx}: cancelled by operator.",
                )
                self.checkpoint.failure_diagnosis = FailureDiagnosis(
                    category=FailureCategory.CANCELLED,
                    message="Task execution was cancelled by operator request.",
                    recoverable=False,
                    suggested_recovery="Run was cancelled by operator.",
                )
                self._save_checkpoint()
                return self._build_response(RunStatus.FAILED)

            step = plan[idx]
            self.checkpoint.current_step_index = idx

            # Skip already completed steps (for safe checkpoint resumption)
            if step.status == StepStatus.COMPLETED:
                continue

            # Check step dependencies
            if step.depends_on:
                completed_ids = {s.id for s in plan if s.status == StepStatus.COMPLETED}
                missing = [dep for dep in step.depends_on if dep not in completed_ids]
                if missing:
                    err_msg = (
                        f"Step '{step.id}' blocked: prerequisite step(s) {missing} not completed."
                    )
                    step.status = StepStatus.FAILED
                    step.error = err_msg
                    self.checkpoint.failure_diagnosis = FailureDiagnosis(
                        category=FailureCategory.VALIDATION_FAILURE,
                        message=err_msg,
                        recoverable=False,
                        suggested_recovery="Ensure prerequisite steps complete successfully.",
                    )
                    self._emit(RunStatus.FAILED, err_msg)
                    self._save_checkpoint()
                    return self._build_response(RunStatus.FAILED)

            if not step.tool:
                step.status = StepStatus.COMPLETED
                self._save_checkpoint()
                continue

            # Approval check for non-dry-run mutations
            diff_text = extract_proposed_diff(plan, self.task.repository)
            fingerprint = compute_plan_fingerprint(plan, diff_text=diff_text)
            now_iso = datetime.now(UTC).isoformat()

            if step.requires_approval and not auto_approved and not self.task.auto_approve:
                self.checkpoint.approval_request = ApprovalRequest(
                    plan_fingerprint=fingerprint,
                    proposed_diff_hash=hashlib.sha256(diff_text.encode("utf-8")).hexdigest()
                    if diff_text
                    else None,
                    requested_at=now_iso,
                    approved=False,
                )
                self._emit(
                    RunStatus.AWAITING_APPROVAL,
                    f"Action '{step.id}' requires explicit operator approval before applying mutations (Fingerprint: {fingerprint[:12]}).",
                )
                self._save_checkpoint()
                return self._build_response(RunStatus.AWAITING_APPROVAL)

            # Cryptographic Approval Invalidation Check
            if auto_approved and self.checkpoint.approval_request:
                current_fingerprint = compute_plan_fingerprint(plan, diff_text=diff_text)
                if current_fingerprint != self.checkpoint.approval_request.plan_fingerprint:
                    self.checkpoint.approval_request.invalidated = True
                    self.checkpoint.approval_request.invalidation_reason = (
                        "Execution plan or proposed diff was modified after approval was requested."
                    )
                    diag = FailureDiagnosis(
                        category=FailureCategory.APPROVAL_INVALIDATED,
                        message="Approval invalidated: execution plan or proposed diff changed after approval request.",
                        recoverable=True,
                        suggested_recovery="Review updated plan and grant renewed operator approval.",
                    )
                    self.checkpoint.failure_diagnosis = diag
                    self._emit(
                        RunStatus.FAILED,
                        f"Approval Invalidated: Plan fingerprint mismatch ({current_fingerprint[:12]} != {self.checkpoint.approval_request.plan_fingerprint[:12]}). Renewed approval required.",
                    )
                    self._save_checkpoint()
                    return self._build_response(RunStatus.FAILED)

                self.checkpoint.approval_request.approved = True
                self.checkpoint.approval_request.approved_at = now_iso

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

            # Idempotency check via Operation Journal
            input_hash = hashlib.sha256(json.dumps(tool_args, sort_keys=True).encode()).hexdigest()[
                :16
            ]
            idempotency_key = hashlib.sha256(
                f"{self.run_id}:{step.id}:{input_hash}".encode()
            ).hexdigest()[:16]

            existing_op = self.store.get_operation_by_idempotency_key(idempotency_key)
            if existing_op and existing_op.state == OperationState.SUCCEEDED:
                self._emit(
                    RunStatus.EXECUTING,
                    f"Step '{step.id}' skipped: operation {existing_op.operation_id} already succeeded (idempotent replay).",
                )
                if existing_op.result:
                    step.output = existing_op.result
                    self.tool_results.append({"tool": step.tool, "result": existing_op.result})
                step.status = StepStatus.COMPLETED
                self._save_checkpoint()
                continue

            if existing_op and existing_op.state == OperationState.RECONCILIATION_REQUIRED:
                self._emit(
                    RunStatus.RECONCILIATION_REQUIRED,
                    f"Step '{step.id}' is blocked: operation {existing_op.operation_id} requires manual reconciliation.",
                )
                self._save_checkpoint()
                return self._build_response(RunStatus.RECONCILIATION_REQUIRED)

            # Pre-compute condition hashes for workspace mutations
            pre_hash = None
            post_hash = None
            if step.tool == "workspace.plan":
                repo_root = str(self.task.repository or ".")
                temp_executor = WorkspaceExecutor(
                    repo_root, dry_run=bool(tool_args.get("dry_run", True))
                )
                try:
                    action = WorkspaceAction(
                        kind=str(tool_args.get("kind", "write")),
                        path=str(tool_args.get("path", "agent-plan.txt")),
                        content=str(tool_args.get("content", "")),
                    )
                    pre_hash, post_hash = temp_executor.compute_conditions(action)
                except ValueError as exc:
                    self._emit(RunStatus.FAILED, f"Condition hashing failed: {exc}")
                    step.status = StepStatus.FAILED
                    self._save_checkpoint()
                    return self._build_response(RunStatus.FAILED)

            # Register operation as PREPARED
            op = JournalOperation(
                operation_id=f"op_{uuid.uuid4().hex[:10]}",
                run_id=self.run_id,
                step_id=step.id,
                idempotency_key=idempotency_key,
                tool=step.tool,
                input_hash=input_hash,
                inputs=tool_args,
                precondition_hash=pre_hash,
                postcondition_hash=post_hash,
                state=OperationState.PREPARED,
                execution_attempt=1,
                started_at=datetime.now(UTC).isoformat(),
            )
            self.store.create_operation(op)

            # Step Execution Loop with Retry & Backoff
            step.status = StepStatus.RUNNING
            self._save_checkpoint()

            while step.status != StepStatus.COMPLETED:
                # Check cancellation inside loop
                if self.checkpoint.cancellation_requested:
                    step.status = StepStatus.SKIPPED
                    self.store.update_operation_state(
                        op.operation_id, OperationState.CANCELLED, error="Run cancelled"
                    )
                    self._emit(RunStatus.FAILED, "Execution cancelled by operator.")
                    self.checkpoint.failure_diagnosis = FailureDiagnosis(
                        category=FailureCategory.CANCELLED,
                        message="Run was cancelled by operator request.",
                        recoverable=False,
                        suggested_recovery="Task cancelled.",
                    )
                    self._save_checkpoint()
                    return self._build_response(RunStatus.FAILED)

                self.store.update_operation_state(
                    op.operation_id,
                    OperationState.RUNNING,
                    execution_attempt=self.retry_count + 1,
                )
                try:
                    output, record = self.registry.execute_guarded(step.tool, tool_args)
                    if output.get("exit_code") not in (0, None) and not output.get("applied", True):
                        error_detail = output.get("stderr") or output.get(
                            "detail", "Non-zero exit code"
                        )
                        raise RuntimeError(error_detail)
                    step.output = output
                    step.status = StepStatus.COMPLETED
                    self.tool_results.append({"tool": step.tool, "result": output})
                    self.evidence_records.append(record)
                    self.store.append_evidence(self.run_id, record)
                    self.store.update_operation_state(
                        op.operation_id, OperationState.SUCCEEDED, result=output
                    )
                    self._emit(
                        RunStatus.EXECUTING,
                        f"Step '{step.id}' completed ({step.tool}).",
                    )
                    break
                except (ValueError, RuntimeError, OSError, TimeoutError) as exc:
                    diagnosis = classify_failure(str(exc))
                    self.checkpoint.failure_diagnosis = diagnosis
                    self.store.update_operation_state(
                        op.operation_id, OperationState.FAILED, error=str(exc)
                    )
                    self.evidence_records.append(
                        EvidenceRecord(
                            source=step.tool,
                            category="tool_failure",
                            summary=f"Tool {step.tool} failed at step '{step.id}': {exc}",
                            passed=False,
                            data={"step_id": step.id, "error": str(exc)},
                        )
                    )

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
        ts = datetime.now(UTC).isoformat()
        results = [
            VerificationResult(
                check="plan_exists",
                passed=bool(plan),
                detail="Plan is non-empty.",
                category="planning",
                expected="Non-empty plan",
                actual=f"{len(plan)} plan step(s)",
                timestamp=ts,
            ),
            VerificationResult(
                check="repository_context",
                passed=self.task.repository is None or repository is not None,
                detail="Repository context was inspected when requested.",
                category="repository",
                expected="Repository context available",
                actual="Context available" if repository else "N/A",
                timestamp=ts,
            ),
            VerificationResult(
                check="tool_allowlist",
                passed=all(
                    step.tool is None or self.policy.authorize(ToolCall(tool=step.tool)).allowed
                    for step in plan
                ),
                detail="Declared tools are policy-approved.",
                category="policy",
                expected="All tools allowlisted",
                actual="All tools approved",
                timestamp=ts,
            ),
        ]

        verification_tool = next(
            (item["result"] for item in self.tool_results if item["tool"] == "verification.run"),
            None,
        )
        if isinstance(verification_tool, dict):
            raw_checks = verification_tool.get("checks")
            checks_list: list[Any] = raw_checks if isinstance(raw_checks, list) else []
            results.extend(
                VerificationResult(**item) for item in checks_list if isinstance(item, dict)
            )

        self.checkpoint.verification = results

        if not all(result.passed for result in results):
            if self._attempt_self_healing_repair(results):
                # Re-verify after autonomous self-healing patch
                return self.execute(auto_approved=auto_approved)

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
        if status in (
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.AWAITING_APPROVAL,
            RunStatus.RECONCILIATION_REQUIRED,
        ):
            get_event_bus().close_run(self.run_id)
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
            "failure_diagnosis": (
                self.checkpoint.failure_diagnosis.model_dump()
                if self.checkpoint.failure_diagnosis
                else None
            ),
            "checkpoint": self.checkpoint.model_dump(),
            "operations": [
                op.model_dump() for op in self.store.list_operations_for_run(self.run_id)
            ],
        }


_RUN_LOCKS_MUTEX = threading.Lock()
_RUN_LOCKS: dict[str, threading.Lock] = {}


def _get_run_lock(run_id: str) -> threading.Lock:
    with _RUN_LOCKS_MUTEX:
        if run_id not in _RUN_LOCKS:
            _RUN_LOCKS[run_id] = threading.Lock()
        return _RUN_LOCKS[run_id]


def resume_run(
    run_id: str,
    approved: bool = False,
    registry: ToolRegistry | None = None,
    policy: ToolPolicy | None = None,
    store: RunStore | None = None,
    expected_fingerprint: str | None = None,
) -> dict[str, object]:
    """Resume an existing run from its stored checkpoint, honoring operator approval and fingerprint validation."""
    lock = _get_run_lock(run_id)
    with lock:
        effective_store = store or get_default_store()
        checkpoint = effective_store.get_checkpoint(run_id)
        if not checkpoint:
            raise ValueError(f"Run '{run_id}' not found in checkpoint store.")

        # Guard against duplicate concurrent execution when already completed
        if checkpoint.status == RunStatus.COMPLETED:
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
            return runner._build_response(RunStatus.COMPLETED)

        # Check operator explicit rejection
        if not approved:
            checkpoint.status = RunStatus.FAILED
            checkpoint.failure_diagnosis = FailureDiagnosis(
                category=FailureCategory.POLICY_VIOLATION,
                message="Operator rejected proposed workspace mutations.",
                recoverable=False,
                suggested_recovery="Review and re-dispatch with modified task constraints.",
            )
            effective_store.save_checkpoint(checkpoint)
            from .policy import ToolPolicy
            from .tools import build_default_registry

            runner = AgentRun(
                task=checkpoint.task,
                registry=registry or build_default_registry(),
                policy=policy or ToolPolicy(),
                run_id=checkpoint.run_id,
                store=effective_store,
                existing_checkpoint=checkpoint,
            )
            runner._emit(RunStatus.FAILED, "Operator rejected proposed workspace mutations.")
            return runner._build_response(RunStatus.FAILED)

        # Fingerprint check if provided
        if (
            expected_fingerprint
            and checkpoint.approval_request
            and checkpoint.approval_request.plan_fingerprint != expected_fingerprint
        ):
            checkpoint.approval_request.invalidated = True
            checkpoint.approval_request.invalidation_reason = f"Provided approval fingerprint '{expected_fingerprint}' does not match stored fingerprint."
            effective_store.save_checkpoint(checkpoint)
            raise ValueError("Approval fingerprint mismatch. Plan may have changed.")

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
