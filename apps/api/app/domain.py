from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    INTAKE = "intake"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class OperationState(str, Enum):
    PENDING = "pending"
    PREPARED = "prepared"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    CANCELLED = "cancelled"


class FailureCategory(str, Enum):
    POLICY_VIOLATION = "policy_violation"
    VALIDATION_FAILURE = "validation_failure"
    EXECUTION_ERROR = "execution_error"
    TIMEOUT = "timeout"
    DEPENDENCY_MISSING = "dependency_missing"
    SYNTAX_ERROR = "syntax_error"
    RECOVERY_REQUIRED = "recovery_required"
    CANCELLED = "cancelled"
    STRATEGY_LOOP = "strategy_loop"
    APPROVAL_INVALIDATED = "approval_invalidated"
    UNKNOWN = "unknown"


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    repository: str | None = Field(default=None, max_length=500)
    constraints: list[str] = Field(default_factory=list, max_length=30)
    dry_run: bool = Field(default=True)
    auto_approve: bool = Field(default=False)
    max_retries: int = Field(default=2, ge=0, le=10)
    expected_files: list[str] = Field(default_factory=list, max_length=50)


class PlanStep(BaseModel):
    id: str
    description: str
    tool: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: list[str] = Field(default_factory=list)
    validation_criteria: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    status: StepStatus = Field(default=StepStatus.PENDING)
    output: dict[str, Any] | None = None
    error: str | None = None
    requires_approval: bool = False
    attempt: int = Field(default=1, ge=1)


class ApprovalRequest(BaseModel):
    plan_fingerprint: str
    proposed_diff_hash: str | None = None
    workspace_pre_state_hash: str | None = None
    target_files: list[str] = Field(default_factory=list)
    requested_at: str
    expires_at: str | None = None
    approved: bool = False
    approved_by: str | None = None
    approved_at: str | None = None
    invalidated: bool = False
    invalidation_reason: str | None = None


class JournalOperation(BaseModel):
    operation_id: str
    run_id: str
    step_id: str
    idempotency_key: str
    tool: str
    input_hash: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    precondition_hash: str | None = None
    postcondition_hash: str | None = None
    state: OperationState = Field(default=OperationState.PENDING)
    execution_attempt: int = Field(default=1, ge=1)
    result: dict[str, Any] | None = None
    error: str | None = None
    recovery_status: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    check: str
    passed: bool
    detail: str
    step_id: str | None = None
    category: str = "general"
    expected: str | None = None
    actual: str | None = None
    timestamp: str | None = None


class RunEvent(BaseModel):
    sequence: int
    status: RunStatus
    message: str
    timestamp: str | None = None


class FailureDiagnosis(BaseModel):
    category: FailureCategory
    message: str
    recoverable: bool
    suggested_recovery: str


class EvidenceRecord(BaseModel):
    source: str
    category: str
    summary: str
    passed: bool
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: str | None = None


class RunCheckpoint(BaseModel):
    run_id: str
    task: TaskSpec
    plan: list[PlanStep] = Field(default_factory=list)
    current_step_index: int = 0
    status: RunStatus = RunStatus.INTAKE
    retry_count: int = 0
    max_retries: int = 2
    events: list[RunEvent] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    verification: list[VerificationResult] = Field(default_factory=list)
    evidence_records: list[EvidenceRecord] = Field(default_factory=list)
    repository_summary: dict[str, Any] | None = None
    failure_diagnosis: FailureDiagnosis | None = None
    approval_request: ApprovalRequest | None = None
    cancellation_requested: bool = False
    created_at: str | None = None
    updated_at: str | None = None
