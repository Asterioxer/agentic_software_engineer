from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.worktree import WorktreeError, WorktreeManager


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test Agent"], cwd=str(path), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@agent.local"],
        cwd=str(path),
        check=True,
        capture_output=True,
    )
    readme = path / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"], cwd=str(path), check=True, capture_output=True
    )


def test_non_git_repo(tmp_path: Path) -> None:
    mgr = WorktreeManager(tmp_path)
    assert not mgr.is_git_repository()
    assert mgr.list_worktrees() == []

    with pytest.raises(WorktreeError, match="not a git repository"):
        mgr.create_worktree("task-1")


def test_worktree_lifecycle(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    mgr = WorktreeManager(repo_dir)
    assert mgr.is_git_repository()

    initial_worktrees = mgr.list_worktrees()
    assert len(initial_worktrees) == 1

    # Create worktree
    wt_path = mgr.create_worktree("fix-101")
    assert wt_path.exists()
    assert (wt_path / "README.md").exists()

    # Verify isolated mutation
    (wt_path / "new_file.py").write_text("x = 1\n", encoding="utf-8")
    assert (wt_path / "new_file.py").exists()
    assert not (repo_dir / "new_file.py").exists()

    # List worktrees
    wts = mgr.list_worktrees()
    assert len(wts) == 2

    # Remove worktree
    removed = mgr.remove_worktree("fix-101", delete_branch=True)
    assert removed
    assert not wt_path.exists()
    assert len(mgr.list_worktrees()) == 1


def test_worktree_context_manager(tmp_path: Path) -> None:
    repo_dir = tmp_path / "repo_ctx"
    repo_dir.mkdir()
    _init_git_repo(repo_dir)

    mgr = WorktreeManager(repo_dir)
    task_id = "ctx-task"

    with mgr.worktree_context(task_id, cleanup=True) as wt_path:
        assert wt_path.exists()
        assert (wt_path / "README.md").exists()

    # Auto-cleanup should remove it
    assert not wt_path.exists()
