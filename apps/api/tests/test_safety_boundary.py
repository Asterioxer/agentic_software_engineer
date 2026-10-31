from pathlib import Path

import pytest

from app.domain import ToolCall
from app.execution import WorkspaceAction, WorkspaceExecutor
from app.policy import ToolPolicy


def test_path_null_bytes_rejected(tmp_path: Path) -> None:
    executor = WorkspaceExecutor(str(tmp_path), dry_run=True)
    with pytest.raises(ValueError, match="null bytes"):
        executor.apply(WorkspaceAction(kind="write", path="sub/test\0.txt", content="hack"))


def test_modifying_git_internals_rejected(tmp_path: Path) -> None:
    executor = WorkspaceExecutor(str(tmp_path), dry_run=False)
    with pytest.raises(
        ValueError, match="Direct modification of VCS internals or environment files is forbidden"
    ):
        executor.apply(WorkspaceAction(kind="write", path=".git/config", content="corrupted"))


def test_modifying_env_file_rejected(tmp_path: Path) -> None:
    executor = WorkspaceExecutor(str(tmp_path), dry_run=False)
    with pytest.raises(
        ValueError, match="Direct modification of VCS internals or environment files is forbidden"
    ):
        executor.apply(WorkspaceAction(kind="write", path=".env", content="SECRET=leaked"))


def test_tool_policy_risk_classification() -> None:
    policy = ToolPolicy()

    # Dry-run write is low risk
    call_dry = ToolCall(tool="workspace.plan", arguments={"dry_run": True})
    assert policy.classify_risk(call_dry) == "low"
    assert not policy.requires_operator_approval(call_dry)

    # Real mutation write is high risk
    call_real = ToolCall(tool="workspace.plan", arguments={"dry_run": False})
    assert policy.classify_risk(call_real) == "high"
    assert policy.requires_operator_approval(call_real)

    # Command run is medium risk
    call_cmd = ToolCall(tool="command.run", arguments={"command_id": "python.tests"})
    assert policy.classify_risk(call_cmd) == "medium"
    assert not policy.requires_operator_approval(call_cmd)
