from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.domain import FailureCategory, RunStatus, TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun, resume_run
from app.store import RunStore
from app.tools import build_default_registry


def test_approval_request_expiration_rejection(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_ttl.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Mutate configuration",
        description="Write configuration file into repository",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=False,
    )

    run = AgentRun(task, registry, policy, store=store)
    result = run.execute()
    run_id = str(result["run_id"])

    assert result["status"] == RunStatus.AWAITING_APPROVAL.value
    checkpoint = store.get_checkpoint(run_id)
    assert checkpoint is not None
    assert checkpoint.approval_request is not None
    assert checkpoint.approval_request.expires_at is not None

    # Simulate expired TTL by moving expires_at to 2 hours ago
    expired_time = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    checkpoint.approval_request.expires_at = expired_time
    store.save_checkpoint(checkpoint)

    # Attempting to resume must raise ValueError and invalidate approval
    with pytest.raises(ValueError, match="Approval request has expired"):
        resume_run(
            run_id=run_id,
            approved=True,
            registry=registry,
            policy=policy,
            store=store,
        )

    updated_cp = store.get_checkpoint(run_id)
    assert updated_cp is not None
    assert updated_cp.approval_request is not None
    assert updated_cp.approval_request.invalidated is True
    assert updated_cp.approval_request.invalidation_reason is not None
    assert "expired" in updated_cp.approval_request.invalidation_reason.lower()
    assert updated_cp.status == RunStatus.FAILED
    assert updated_cp.failure_diagnosis is not None
    assert updated_cp.failure_diagnosis.category == FailureCategory.APPROVAL_INVALIDATED
