from pathlib import Path

from app.domain import RunStatus, TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun, resume_run
from app.store import RunStore
from app.tools import build_default_registry


def test_agent_run_pauses_for_approval_when_mutating(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    # Task with real mutation (dry_run=False) and auto_approve=False
    task = TaskSpec(
        title="Apply real file change",
        description="Write actual file into repository",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=False,
    )

    run = AgentRun(task, registry, policy, store=store)
    result = run.execute()

    assert result["status"] == RunStatus.AWAITING_APPROVAL.value
    run_id = str(result["run_id"])

    # Now resume with explicit operator approval
    resumed_result = resume_run(run_id, approved=True, registry=registry, policy=policy, store=store)
    assert resumed_result["status"] == RunStatus.COMPLETED.value
    assert (tmp_path / "agent-plan.txt").exists()


def test_agent_run_does_not_repeat_completed_steps_on_resume(tmp_path: Path) -> None:
    store = RunStore(str(tmp_path / "test.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Execute bounded change",
        description="Write file into repository",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=False,
    )

    run = AgentRun(task, registry, policy, store=store)
    res1 = run.execute()
    assert res1["status"] == RunStatus.AWAITING_APPROVAL.value

    # Checkpoint has step 0 (understand) and step 1 (inspect) completed
    checkpoint = store.get_checkpoint(str(res1["run_id"]))
    assert checkpoint is not None
    assert checkpoint.plan[0].status.value == "completed"

    # Resume and verify completion
    res2 = resume_run(str(res1["run_id"]), approved=True, registry=registry, policy=policy, store=store)
    assert res2["status"] == RunStatus.COMPLETED.value
