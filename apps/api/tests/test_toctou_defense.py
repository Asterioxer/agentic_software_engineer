from __future__ import annotations

from pathlib import Path

import pytest

from app.domain import FailureCategory, RunStatus, TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun, resume_run
from app.store import RunStore
from app.tools import build_default_registry


def test_toctou_disk_mutation_interception(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_toctou.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    # Pre-create target file
    target_file = tmp_path / "agent-plan.txt"
    target_file.write_text("initial plan\n", encoding="utf-8")

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
    assert checkpoint.approval_request.workspace_pre_state_hash is not None

    # External actor mutates target file behind the scenes
    target_file.write_text("tampered plan\n", encoding="utf-8")

    # Resumption must detect TOCTOU divergence and fail
    with pytest.raises(ValueError, match="TOCTOU workspace divergence"):
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
    assert "toctou divergence" in updated_cp.approval_request.invalidation_reason.lower()
    assert updated_cp.status == RunStatus.FAILED
    assert updated_cp.failure_diagnosis is not None
    assert updated_cp.failure_diagnosis.category == FailureCategory.APPROVAL_INVALIDATED
