from __future__ import annotations

import logging
import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("agent.worktree")


@dataclass(frozen=True)
class WorktreeInfo:
    worktree_path: str
    head_commit: str
    branch: str | None


class WorktreeError(RuntimeError):
    """Raised when git worktree operations fail."""


class WorktreeManager:
    """Manages ephemeral git worktrees for isolated task execution.

    Provides workspace isolation so autonomous mutations and tests do not
    contaminate the primary repository working directory.
    """

    def __init__(self, repo_root: str | Path, worktrees_dir: str | Path | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        if worktrees_dir:
            self.worktrees_dir = Path(worktrees_dir).resolve()
        else:
            self.worktrees_dir = self.repo_root / ".agent_worktrees"

    def _run_git(self, args: list[str], cwd: Path | None = None) -> str:
        cmd = ["git"] + args
        work_dir = cwd or self.repo_root
        try:
            res = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if res.returncode != 0:
                err_msg = res.stderr.strip() or res.stdout.strip()
                raise WorktreeError(f"Git command {' '.join(args)} failed: {err_msg}")
            return res.stdout.strip()
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise WorktreeError(f"Git execution error: {exc}") from exc

    def is_git_repository(self) -> bool:
        """Verify whether repo_root is a valid git repository."""
        try:
            out = self._run_git(["rev-parse", "--is-inside-work-tree"])
            return out == "true"
        except WorktreeError:
            return False

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List active git worktrees."""
        if not self.is_git_repository():
            return []

        out = self._run_git(["worktree", "list", "--porcelain"])
        worktrees: list[WorktreeInfo] = []
        current_path: str | None = None
        current_head: str | None = None
        current_branch: str | None = None

        for line in out.splitlines():
            line = line.strip()
            if not line:
                if current_path and current_head:
                    worktrees.append(WorktreeInfo(current_path, current_head, current_branch))
                current_path, current_head, current_branch = None, None, None
                continue
            if line.startswith("worktree "):
                current_path = line[len("worktree ") :].strip()
            elif line.startswith("HEAD "):
                current_head = line[len("HEAD ") :].strip()
            elif line.startswith("branch "):
                current_branch = line[len("branch ") :].strip()

        if current_path and current_head:
            worktrees.append(WorktreeInfo(current_path, current_head, current_branch))

        return worktrees

    def create_worktree(self, task_id: str, base_ref: str = "HEAD") -> Path:
        """Create an ephemeral worktree on a dedicated agent branch."""
        if not self.is_git_repository():
            raise WorktreeError(f"Directory '{self.repo_root}' is not a git repository.")

        sanitized_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_id)
        branch_name = f"agent/{sanitized_id}"
        target_path = self.worktrees_dir / sanitized_id

        # Ensure parent dir exists
        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

        if target_path.exists():
            # Clean up pre-existing worktree at that path
            self.remove_worktree(sanitized_id, delete_branch=True)

        logger.info("Creating git worktree at %s on branch %s", target_path, branch_name)
        self._run_git(["worktree", "add", "-b", branch_name, str(target_path), base_ref])
        return target_path

    def remove_worktree(self, task_id: str, delete_branch: bool = True) -> bool:
        """Remove an ephemeral worktree and optionally prune its branch."""
        sanitized_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_id)
        target_path = self.worktrees_dir / sanitized_id
        branch_name = f"agent/{sanitized_id}"

        removed = False
        try:
            self._run_git(["worktree", "remove", "--force", str(target_path)])
            removed = True
        except WorktreeError as exc:
            logger.debug("Worktree remove returned error (may already be deleted): %s", exc)

        try:
            self._run_git(["worktree", "prune"])
        except WorktreeError:
            pass

        if delete_branch:
            try:
                self._run_git(["branch", "-D", branch_name])
            except WorktreeError as exc:
                logger.debug("Branch delete returned error (may not exist): %s", exc)

        return removed

    @contextmanager
    def worktree_context(
        self,
        task_id: str,
        base_ref: str = "HEAD",
        cleanup: bool = False,
    ) -> Generator[Path, None, None]:
        """Context manager creating a temporary worktree and optionally cleaning it up."""
        wt_path = self.create_worktree(task_id, base_ref=base_ref)
        try:
            yield wt_path
        finally:
            if cleanup:
                self.remove_worktree(task_id, delete_branch=True)
