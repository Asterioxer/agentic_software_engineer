import hashlib
from pathlib import Path

from app.domain import OperationState, RunStatus, TaskSpec
from app.execution import compute_file_hash
from app.policy import ToolPolicy
from app.runner import AgentRun, resume_run
from app.store import RunStore
from app.tools import build_default_registry


def test_operation_journal_records_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "journal_test.db"
    store = RunStore(str(db_path))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Journal test",
        description="Verify operations are logged in SQLite journal",
        repository=str(tmp_path),
        dry_run=True,
    )

    run = AgentRun(task, registry, policy, store=store)
    res = run.execute()
    assert res["status"] == RunStatus.COMPLETED.value

    ops = store.list_operations_for_run(run.run_id)
    assert len(ops) >= 2  # repository.inspect and workspace.plan
    for op in ops:
        assert op.state == OperationState.SUCCEEDED
        assert op.idempotency_key
        assert op.input_hash
        assert op.started_at
        assert op.completed_at


def test_operation_idempotency_prevents_duplicate_mutation(tmp_path: Path) -> None:
    db_path = tmp_path / "journal_idempotency.db"
    store = RunStore(str(db_path))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Idempotent mutation",
        description="Ensure file write is not repeated if journal says SUCCEEDED",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=True,
    )

    run = AgentRun(task, registry, policy, store=store)
    res1 = run.execute()
    assert res1["status"] == RunStatus.COMPLETED.value
    target_file = tmp_path / "agent-plan.txt"
    assert target_file.exists()

    # Re-run same run_id: should replay idempotently without re-writing
    initial_mtime = target_file.stat().st_mtime_ns

    run2 = AgentRun(task, registry, policy, run_id=run.run_id, store=store)
    res2 = run2.execute(auto_approved=True)
    assert res2["status"] == RunStatus.COMPLETED.value

    # File modification time should be identical (no re-write performed)
    assert target_file.stat().st_mtime_ns == initial_mtime


def test_crash_recovery_reconciles_from_postcondition(tmp_path: Path) -> None:
    db_path = tmp_path / "crash_recon.db"
    store = RunStore(str(db_path))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Crash recovery test",
        description="Simulate crash right after file write before checkpoint save",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=True,
    )

    run = AgentRun(task, registry, policy, store=store)
    # Start run to populate plan and initial checkpoint
    _plan, _summary = run.checkpoint.plan, run.checkpoint.repository_summary
    run._emit(RunStatus.INTAKE, "Task accepted.")
    run._save_checkpoint()

    # Simulate: file was written to disk
    target_file = tmp_path / "agent-plan.txt"
    content = f"# Plan: {task.title}\n\n{task.description}\n"
    target_file.write_text(content, encoding="utf-8")
    actual_hash = compute_file_hash(target_file)

    # Simulate: operation was left in RUNNING state (crash before SUCCEEDED update)
    input_hash = hashlib.sha256(b"simulated_args").hexdigest()[:16]
    idempotency_key = hashlib.sha256(f"{run.run_id}:implement:{input_hash}".encode()).hexdigest()[
        :16
    ]

    from app.domain import JournalOperation

    op = JournalOperation(
        operation_id="op-crashed-1",
        run_id=run.run_id,
        step_id="implement",
        idempotency_key=idempotency_key,
        tool="workspace.plan",
        input_hash=input_hash,
        inputs={"path": "agent-plan.txt", "content": content},
        precondition_hash="ABSENT",
        postcondition_hash=actual_hash,
        state=OperationState.RUNNING,
    )
    store.create_operation(op)

    # Resume the crashed run
    recovered_res = resume_run(
        run.run_id, approved=True, registry=registry, policy=policy, store=store
    )
    assert recovered_res["status"] == RunStatus.COMPLETED.value

    # Check that operation was reconciled
    updated_op = store.get_operation("op-crashed-1")
    assert updated_op is not None
    assert updated_op.state == OperationState.SUCCEEDED
    assert updated_op.recovery_status == "reconciled_from_postcondition"


def test_crash_recovery_detects_corrupted_divergence(tmp_path: Path) -> None:
    db_path = tmp_path / "crash_diverged.db"
    store = RunStore(str(db_path))
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Divergence test",
        description="Simulate file corrupted externally during crash",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=True,
    )

    run = AgentRun(task, registry, policy, store=store)
    run._emit(RunStatus.INTAKE, "Task accepted.")
    run._save_checkpoint()

    # File exists but has corrupted/unexpected content
    target_file = tmp_path / "agent-plan.txt"
    target_file.write_text("CORRUPTED BY CRASH / SYSTEM ANOMALY", encoding="utf-8")

    from app.domain import JournalOperation

    input_hash = "mock_hash_123"
    op = JournalOperation(
        operation_id="op-diverged-1",
        run_id=run.run_id,
        step_id="implement",
        idempotency_key="idemp-diverged",
        tool="workspace.plan",
        input_hash=input_hash,
        inputs={"path": "agent-plan.txt"},
        precondition_hash="ABSENT",
        postcondition_hash="EXPECTED_HASH_NEVER_MATCHED",
        state=OperationState.RUNNING,
    )
    store.create_operation(op)

    recovered = resume_run(run.run_id, approved=True, registry=registry, policy=policy, store=store)
    assert recovered["status"] == RunStatus.RECONCILIATION_REQUIRED.value

    updated_op = store.get_operation("op-diverged-1")
    assert updated_op is not None
    assert updated_op.state == OperationState.RECONCILIATION_REQUIRED
    assert updated_op.recovery_status == "hash_diverged_from_expected"
