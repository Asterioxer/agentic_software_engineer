from pathlib import Path
import pytest
from app.execution import WorkspaceAction,WorkspaceExecutor
from app.execution_policy import ExecutionPolicy
def test_dry_run_does_not_mutate(tmp_path:Path)->None:
    result=WorkspaceExecutor(str(tmp_path)).apply(WorkspaceAction(kind="write",path="hello.txt",content="hello"))
    assert not result.applied and not (tmp_path/"hello.txt").exists()
def test_execution_rejects_path_escape(tmp_path:Path)->None:
    with pytest.raises(ValueError,match="escapes"): WorkspaceExecutor(str(tmp_path)).apply(WorkspaceAction(kind="write",path="../escape.txt",content="nope"))
def test_policy_bounds_actions()->None:
    actions=[WorkspaceAction(kind="write",path=f"{i}.txt",content="x") for i in range(21)]
    assert not ExecutionPolicy().authorize(actions).allowed
