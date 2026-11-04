from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .domain import (
    EvidenceRecord,
    FailureCategory,
    FailureDiagnosis,
    JournalOperation,
    OperationState,
    RunCheckpoint,
    RunEvent,
    RunStatus,
    StepStatus,
    TaskSpec,
    ToolCall,
    VerificationResult,
)
from .execution import WorkspaceAction, WorkspaceExecutor, compute_file_hash
from .llm import repair_code
from .planner import plan_with_repository
from .policy import ToolPolicy
from .reflection import classify_failure, reflect
from .store import RunStore, get_default_store
from .telemetry import get_event_bus
from .tools import ToolRegistry


class AgentRun:
    """Resilient, auditable control-plane runner with persistent checkpoint recovery and operation journaling."""

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
        get_event_bus().publish(
            self.run_id,
            event_type=f"status:{status.value}",
            payload={"sequence": event.sequence, "status": status.value, "message": message},
        )

    def _save_checkpoint(self) -> None:
        self.checkpoint.events = list(self.events)
        self.checkpoint.tool_results = list(self.tool_results)
        self.checkpoint.evidence_records = list(self.evidence_records)
        self.store.save_checkpoint(self.checkpoint)

    def _reconcile_interrupted_operations(self) -> bool:
        """Scan and reconcile any operations that were interrupted mid-flight.

        Returns True if clean/reconciled, False if manual reconciliation is required.
        """
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
                target_file: Path | None = None
                if ":" in r.check:
                    cand = r.check.split(":", 1)[1]
                    cand_path = (repo_root / cand).resolve()
                    if cand_path.exists() and cand_path.is_file():
                        target_file = cand_path

                if not target_file:
                    for s in reversed(self.checkpoint.plan):
                        if s.tool in ("workspace.plan", "workspace.patch") and s.inputs:
                            p = s.inputs.get("path")
                            if isinstance(p, str):
                                cand_path = (repo_root / p).resolve()
                                if cand_path.exists() and cand_path.is_file():
                                    target_file = cand_path
                                    break

                if target_file and target_file.exists() and target_file.is_file():
                    try:
                        broken_code = target_file.read_text(encoding="utf-8")
                        repair_res = repair_code(
                            broken_code=broken_code,
                            error_message=f"{r.check}: {r.detail}",
                            test_output=r.detail,
                        )
                        if repair_res.success and repair_res.syntax_valid:
                            self.retry_count += 1
                            self.checkpoint.retry_count = self.retry_count
                            self._emit(
                                RunStatus.REFLECTING,
                                f"Autonomous self-healing attempt {self.retry_count}/{self.max_retries}: repaired {target_file.name}",
                            )
                            if not self.task.dry_run:
                                target_file.write_text(repair_res.repaired_code, encoding="utf-8")
                            repaired = True
                            break
                    except (OSError, UnicodeDecodeError):
                        continue

        return repaired

    def execute(self, auto_approved: bool = False) -> dict[str, object]:
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
                    pre_hash, post_hash = temp_executor.compute_conditions(
                        WorkspaceAction(
                            kind=str(tool_args.get("kind", "write")),
                            path=str(tool_args.get("path", "agent-plan.txt")),
                            content=tool_args.get("content", ""),
                        )
                    )
                except (OSError, ValueError):
                    pre_hash = post_hash = None

            # Create durable Operation Journal record (PREPARED state)
            op_id = uuid.uuid4().hex[:12]
            journal_op = JournalOperation(
                operation_id=op_id,
                run_id=self.run_id,
                step_id=step.id,
                idempotency_key=idempotency_key,
                tool=step.tool,
                input_hash=input_hash,
                inputs=tool_args,
                precondition_hash=pre_hash,
                postcondition_hash=post_hash,
                state=OperationState.PREPARED,
                execution_attempt=existing_op.execution_attempt + 1 if existing_op else 1,
                started_at=datetime.now(UTC).isoformat(),
            )
            self.store.create_operation(journal_op)
            self.store.update_operation_state(op_id, state=OperationState.RUNNING)

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

                    # Update Operation Journal to SUCCEEDED
                    self.store.update_operation_state(
                        op_id,
                        state=OperationState.SUCCEEDED,
                        result=result,
                        postcondition_hash=result.get("postcondition_hash") or post_hash,
                        completed_at=datetime.now(UTC).isoformat(),
                    )
                except (OSError, ValueError, KeyError, RuntimeError) as exc:
                    diagnosis = classify_failure(str(exc), step_output=step.output)
                    self.checkpoint.failure_diagnosis = diagnosis
                    step.error = str(exc)

                    # Update Operation Journal to FAILED
                    self.store.update_operation_state(
                        op_id,
                        state=OperationState.FAILED,
                        error=str(exc),
                        completed_at=datetime.now(UTC).isoformat(),
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
) -> dict[str, object]:
    """Resume an existing run from its stored checkpoint, honoring operator approval."""
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
