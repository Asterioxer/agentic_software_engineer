from __future__ import annotations

import subprocess
from pathlib import Path

from app.domain import TaskSpec
from app.integrations.bot_runner import AutonomousBotRunner


def test_bot_runner_non_git_workspace(tmp_path: Path) -> None:
    runner = AutonomousBotRunner()
    task = TaskSpec(
        title="Check system health",
        description="Verify system integrity",
        repository=str(tmp_path),
        dry_run=True,
    )
    result = runner.execute_bot_task(task)
    assert result.success is True
    assert result.status == "completed"
    assert "Autonomous Engineering Agent Report" in result.pr_comment


def test_bot_runner_git_worktree_execution(tmp_path: Path) -> None:
    # Initialize a dummy git repo
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "TestBot"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "bot@test.local"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )

    readme = tmp_path / "README.md"
    readme.write_text("# Initial Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )

    runner = AutonomousBotRunner()
    task = TaskSpec(
        title="Add healthcheck doc",
        description="Write healthcheck guidelines",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=True,
    )

    result = runner.execute_bot_task(task, cleanup_on_success=True)
    assert result.success is True
    assert result.status == "completed"
    assert "Autonomous Engineering Agent Report" in result.pr_comment
