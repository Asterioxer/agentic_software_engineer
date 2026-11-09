from __future__ import annotations

from pathlib import Path

from app.domain import FailureCategory, PlanStep, RunCheckpoint, RunStatus, StepStatus, TaskSpec
from app.planner import build_deterministic_plan
from app.policy import ToolPolicy
from app.runner import AgentRun
from app.store import RunStore
from app.tools import build_default_registry


def test_planner_generates_typed_dependencies_and_conditions() -> None:
    task = TaskSpec(
        title="Implement logging middleware",
        description="Add custom structured logging middleware to API",
        repository=".",
        dry_run=True,
    )
    plan = build_deterministic_plan(task, repository_summary={"file_count": 5})

    assert len(plan) >= 3
    # Step 0: understand
    step0 = plan[0]
    assert step0.id == "understand"
    assert step0.depends_on == []
    assert len(step0.preconditions) > 0
    assert len(step0.postconditions) > 0

    # Step 1: inspect
    step1 = plan[1]
    assert step1.id == "inspect"
    assert "understand" in step1.depends_on

    # Subsequent mutation/verification steps
    last_step = plan[-1]
    assert last_step.id == "verify"
    assert len(last_step.depends_on) > 0


def test_runner_blocks_step_when_prerequisite_fails(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_dep_blocked.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Blocked dependency test",
        description="Verify prerequisite enforcement",
        repository=str(tmp_path),
        dry_run=True,
    )

    # Construct plan where second step depends on a failed first step
    step_a = PlanStep(
        id="step_a",
        description="Step A",
        tool=None,
        inputs={},
        depends_on=[],
        status=StepStatus.FAILED,
        error="Step A crashed",
    )
    step_b = PlanStep(
        id="step_b",
        description="Step B",
        tool=None,
        inputs={},
        depends_on=["step_a"],
        status=StepStatus.PENDING,
    )

    checkpoint = RunCheckpoint(
        run_id="run_blocked_dep",
        task=task,
        plan=[step_a, step_b],
        current_step_index=1,
        status=RunStatus.EXECUTING,
    )
    store.save_checkpoint(checkpoint)

    runner = AgentRun(
        task=task,
        registry=registry,
        policy=policy,
        store=store,
        existing_checkpoint=checkpoint,
    )
    res = runner.execute()

    assert res["status"] == RunStatus.FAILED.value
    assert runner.checkpoint.failure_diagnosis is not None
    assert runner.checkpoint.failure_diagnosis.category == FailureCategory.VALIDATION_FAILURE
    assert "prerequisite step(s)" in runner.checkpoint.failure_diagnosis.message


def test_runner_succeeds_when_dependencies_fulfilled(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test_dep_ok.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Fulfilled dependency test",
        description="Verify dependent steps succeed",
        repository=str(tmp_path),
        dry_run=True,
    )

    runner = AgentRun(task=task, registry=registry, policy=policy, store=store)
    res = runner.execute()

    assert res["status"] == RunStatus.COMPLETED.value
    # All plan steps should be marked completed
    checkpoint = store.get_checkpoint(runner.run_id)
    assert checkpoint is not None
    assert all(s.status == StepStatus.COMPLETED for s in checkpoint.plan)
