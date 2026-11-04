from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..domain import RunStatus, TaskSpec
from ..policy import ToolPolicy
from ..runner import AgentRun
from ..store import RunStore, get_default_store
from ..tools import ToolRegistry, build_default_registry
from ..worktree import WorktreeManager
from .github import format_github_pr_comment

logger = logging.getLogger("agent.integrations.bot_runner")


@dataclass
class BotExecutionResult:
    success: bool = False
    run_id: str = ""
    status: str = "failed"
    branch: str | None = None
    commit_sha: str | None = None
    pr_comment: str = ""
    changed_files: list[str] = ()  # type: ignore[assignment]
    details: dict[str, Any] | None = None


class AutonomousBotRunner:
    """Orchestrates autonomous bot workflows inside ephemeral git worktrees with verification gating."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        policy: ToolPolicy | None = None,
        store: RunStore | None = None,
    ) -> None:
        self.registry = registry or build_default_registry()
        self.policy = policy or ToolPolicy()
        self.store = store or get_default_store()

    def execute_bot_task(
        self,
        task: TaskSpec,
        base_ref: str = "HEAD",
        cleanup_on_success: bool = False,
    ) -> BotExecutionResult:
        """Execute a task in an isolated ephemeral git worktree, verify, and commit cleanly."""
        if not task.repository:
            # Standalone execution without git isolation
            run = AgentRun(task, self.registry, self.policy, store=self.store)
            res = run.execute()
            comment = format_github_pr_comment(res)
            return BotExecutionResult(
                success=res.get("status") == RunStatus.COMPLETED.value,
                run_id=run.run_id,
                status=str(res.get("status")),
                branch=None,
                commit_sha=None,
                pr_comment=comment,
                changed_files=[],
                details=res,
            )

        repo_root = Path(task.repository).resolve()
        wt_mgr = WorktreeManager(repo_root)

        if not wt_mgr.is_git_repository():
            # Non-git workspace fallback
            run = AgentRun(task, self.registry, self.policy, store=self.store)
            res = run.execute()
            comment = format_github_pr_comment(res)
            return BotExecutionResult(
                success=res.get("status") == RunStatus.COMPLETED.value,
                run_id=run.run_id,
                status=str(res.get("status")),
                branch=None,
                commit_sha=None,
                pr_comment=comment,
                changed_files=[],
                details=res,
            )

        # Ephemeral worktree isolation
        task_sub_id = f"fix_{task.title[:15].strip().replace(' ', '_').lower()}_{int(repo_root.stat().st_mtime)}"
        branch_name = f"bot/{task_sub_id}"
        worktree_path: Path | None = None

        try:
            worktree_path = wt_mgr.create_worktree(task_sub_id, base_ref=base_ref)
            logger.info("Bot runner initialized worktree at %s", worktree_path)

            # Redirect task repository to the isolated worktree
            isolated_task = TaskSpec(
                title=task.title,
                description=task.description,
                repository=str(worktree_path),
                dry_run=task.dry_run,
                auto_approve=task.auto_approve,
                constraints=task.constraints,
                expected_files=task.expected_files,
                max_retries=task.max_retries,
            )

            run = AgentRun(isolated_task, self.registry, self.policy, store=self.store)
            res = run.execute()
            run_status = str(res.get("status"))
            comment = format_github_pr_comment(res)

            is_completed = run_status == RunStatus.COMPLETED.value
            verifications = res.get("verification", [])
            all_passed = bool(
                isinstance(verifications, list)
                and verifications
                and all(
                    v.get("passed", False) if isinstance(v, dict) else getattr(v, "passed", False)
                    for v in verifications
                )
            )

            commit_sha: str | None = None
            changed_files: list[str] = []

            if is_completed and all_passed and not task.dry_run:
                # Stage and commit mutations
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=str(worktree_path),
                    check=False,
                    capture_output=True,
                )
                status_res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(worktree_path),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if status_res.stdout.strip():
                    changed_files = [
                        line[3:].strip() for line in status_res.stdout.strip().splitlines()
                    ]
                    subprocess.run(
                        ["git", "commit", "-m", f"bot: {task.title}\n\nTask-Run-ID: {run.run_id}"],
                        cwd=str(worktree_path),
                        check=False,
                        capture_output=True,
                    )
                    rev_res = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=str(worktree_path),
                        check=False,
                        capture_output=True,
                        text=True,
                    )
                    commit_sha = rev_res.stdout.strip() or None

            return BotExecutionResult(
                success=is_completed and all_passed,
                run_id=run.run_id,
                status=run_status,
                branch=branch_name if commit_sha else None,
                commit_sha=commit_sha,
                pr_comment=comment,
                changed_files=changed_files,
                details=res,
            )

        finally:
            if worktree_path and (cleanup_on_success or not is_completed):
                try:
                    wt_mgr.remove_worktree(task_sub_id, delete_branch=not bool(commit_sha))
                except (OSError, RuntimeError) as exc:
                    logger.warning("Error pruning ephemeral worktree: %s", exc)
