from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from ..domain import TaskSpec

logger = logging.getLogger("agent.integrations.github")


def verify_github_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    secret: str,
) -> bool:
    """Verify GitHub HMAC-SHA256 signature using constant-time digest comparison."""
    if not secret:
        # If no secret configured, skip verification in dev mode
        return True
    if not signature_header:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    expected_sig = signature_header[len(prefix) :]
    computed_sig = hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed_sig, expected_sig)


def parse_github_event(event_type: str, payload: dict[str, Any]) -> TaskSpec | None:
    """Parse a GitHub webhook event payload into a structured TaskSpec."""
    logger.info("Parsing GitHub webhook event: %s", event_type)

    if event_type == "issues":
        action = payload.get("action")
        if action in ("opened", "labeled"):
            issue = payload.get("issue", {})
            title = issue.get("title", "GitHub Issue")
            body = issue.get("body", "") or title
            repo = payload.get("repository", {}).get("full_name")
            desc = (
                f"Repository: {repo}\n\nGitHub Issue Description:\n{body}"
                if repo
                else f"GitHub Issue Description:\n{body}"
            )
            return TaskSpec(
                title=f"[Issue #{issue.get('number', '')}] {title}",
                description=desc,
                repository=None,  # Local checkout or worktree path set by worker
                dry_run=True,
                auto_approve=False,
            )

    elif event_type == "issue_comment":
        action = payload.get("action")
        comment = payload.get("comment", {})
        body = comment.get("body", "").strip()

        # Triggered when comment starts with @agentic-bot fix or /fix
        if action == "created" and any(
            body.startswith(p) for p in ("@agentic-bot fix", "/fix", "@agentic-bot")
        ):
            issue = payload.get("issue", {})
            title = issue.get("title", "Issue Comment Fix")
            return TaskSpec(
                title=f"[Fix #{issue.get('number', '')}] {title}",
                description=f"Issue: {title}\nRequested Instruction:\n{body}",
                dry_run=False,
                auto_approve=False,
            )

    elif event_type == "pull_request":
        action = payload.get("action")
        if action in ("opened", "synchronize"):
            pr = payload.get("pull_request", {})
            title = pr.get("title", "Pull Request Review")
            body = pr.get("body", "") or title
            return TaskSpec(
                title=f"[PR #{pr.get('number', '')}] {title}",
                description=f"Pull Request Review & Verification:\n{body}",
                dry_run=True,
                auto_approve=False,
            )

    return None


def format_github_pr_comment(run_result: dict[str, Any]) -> str:
    """Format an agent execution result into a GitHub markdown PR comment."""
    status = str(run_result.get("status", "unknown")).upper()
    run_id = run_result.get("run_id", "")
    task = run_result.get("task", {})
    title = task.get("title", "Task")

    status_icon = (
        "SUCCESS"
        if status == "COMPLETED"
        else "PAUSED"
        if status == "AWAITING_APPROVAL"
        else "FAILED"
    )

    lines: list[str] = [
        f"### [{status_icon}] Autonomous Engineering Agent Report",
        f"**Task:** {title}",
        f"**Run ID:** `{run_id}` | **Status:** `{status}`\n",
    ]

    # Plan table
    plan = run_result.get("plan", [])
    if plan and isinstance(plan, list):
        lines.append("#### Planned Steps")
        lines.append("| Step | Tool | Status | Description |")
        lines.append("|---|---|---|---|")
        for s in plan:
            if isinstance(s, dict):
                lines.append(
                    f"| `{s.get('id')}` | `{s.get('tool') or '-'}` | `{s.get('status')}` | {s.get('description', '')[:40]} |"
                )
        lines.append("")

    # Verification checks
    verifications = run_result.get("verification", [])
    if verifications and isinstance(verifications, list):
        lines.append("#### Independent Verification Results")
        lines.append("| Check | Result | Details |")
        lines.append("|---|---|---|")
        for v in verifications:
            if isinstance(v, dict):
                res_icon = "PASS" if v.get("passed") else "FAIL"
                lines.append(f"| `{v.get('check')}` | `{res_icon}` | {v.get('detail', '')[:50]} |")
        lines.append("")

    # Security Critic
    critic = run_result.get("failure_diagnosis")
    if critic and isinstance(critic, dict):
        lines.append(
            f"> **Critic / Diagnosis:** `[{critic.get('category')}]` {critic.get('message')}\n"
        )

    lines.append("---\n*Generated deterministically by Agentic Software Engineer Control Plane.*")
    return "\n".join(lines)
