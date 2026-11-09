from __future__ import annotations

from pathlib import Path

import pytest

from app.domain import FailureCategory, RunStatus, TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun, resume_run
from app.store import RunStore
from app.tools import build_default_registry


def test_approval_binding_and_fingerprint_generation(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_approval.db"))
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

    assert result["status"] == RunStatus.AWAITING_APPROVAL.value
    run_id = str(result["run_id"])

    checkpoint = store.get_checkpoint(run_id)
    assert checkpoint is not None
    assert checkpoint.approval_request is not None
    assert checkpoint.approval_request.plan_fingerprint is not None
    assert len(checkpoint.approval_request.plan_fingerprint) == 64
    assert not checkpoint.approval_request.invalidated


def test_approval_resumption_with_valid_fingerprint(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_approval_valid.db"))
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

    checkpoint = store.get_checkpoint(run_id)
    assert checkpoint is not None
    assert checkpoint.approval_request is not None
    fingerprint = checkpoint.approval_request.plan_fingerprint

    # Resuming with matching expected fingerprint succeeds
    res = resume_run(
        run_id=run_id,
        approved=True,
        registry=registry,
        policy=policy,
        store=store,
        expected_fingerprint=fingerprint,
    )
    assert res["status"] == RunStatus.COMPLETED.value


def test_approval_rejected_on_fingerprint_mismatch(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_approval_mismatch.db"))
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

    bogus_fingerprint = "0000000000000000000000000000000000000000000000000000000000000000"

    with pytest.raises(ValueError, match="Approval fingerprint mismatch"):
        resume_run(
            run_id=run_id,
            approved=True,
            registry=registry,
            policy=policy,
            store=store,
            expected_fingerprint=bogus_fingerprint,
        )

    # Verify checkpoint was marked as invalidated
    checkpoint = store.get_checkpoint(run_id)
    assert checkpoint is not None
    assert checkpoint.approval_request is not None
    assert checkpoint.approval_request.invalidated is True
    assert checkpoint.approval_request.invalidation_reason is not None
    assert "does not match" in checkpoint.approval_request.invalidation_reason.lower()


def test_approval_explicit_operator_rejection(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_approval_reject.db"))
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

    # Resume with approved=False
    res = resume_run(
        run_id=run_id,
        approved=False,
        registry=registry,
        policy=policy,
        store=store,
    )

    assert res["status"] == RunStatus.FAILED.value
    checkpoint = store.get_checkpoint(run_id)
    assert checkpoint is not None
    assert checkpoint.failure_diagnosis is not None
    assert checkpoint.failure_diagnosis.category == FailureCategory.POLICY_VIOLATION
    assert "rejected" in checkpoint.failure_diagnosis.message.lower()
