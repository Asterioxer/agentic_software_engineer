from pathlib import Path

from app.domain import EvidenceRecord, RunCheckpoint, RunEvent, RunStatus, TaskSpec
from app.store import RunStore


def test_run_store_save_and_retrieve_checkpoint(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    store = RunStore(str(db_file))

    task = TaskSpec(
        title="Implement audit logger",
        description="Write an audit log feature",
        repository=str(tmp_path),
    )
    checkpoint = RunCheckpoint(
        run_id="run-12345",
        task=task,
        status=RunStatus.EXECUTING,
        current_step_index=1,
    )
    store.save_checkpoint(checkpoint)

    loaded = store.get_checkpoint("run-12345")
    assert loaded is not None
    assert loaded.run_id == "run-12345"
    assert loaded.task.title == "Implement audit logger"
    assert loaded.status == RunStatus.EXECUTING
    assert loaded.current_step_index == 1


def test_run_store_append_events_and_evidence(tmp_path: Path) -> None:
    db_file = tmp_path / "test.db"
    store = RunStore(str(db_file))

    event = RunEvent(sequence=1, status=RunStatus.INTAKE, message="Started run")
    store.append_event("run-abc", event)

    evidence = EvidenceRecord(
        source="command.run",
        category="tool_execution",
        summary="pytest completed successfully",
        passed=True,
        data={"exit_code": 0},
    )
    store.append_evidence("run-abc", evidence)

    runs = store.list_runs()
    assert isinstance(runs, list)
