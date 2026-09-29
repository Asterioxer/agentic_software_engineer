from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

class WorkflowAction(str, Enum):
    CREATE_BRANCH = "create_branch"
    OPEN_PR = "open_pr"
    MERGE_PR = "merge_pr"

@dataclass(frozen=True)
class GitHubWorkflowRequest:
    action: WorkflowAction
    branch: str
    base: str = "main"
    title: str = ""
    body: str = ""
    require_green: bool = True

class GitHubWorkflowPolicy:
    def authorize(self, request: GitHubWorkflowRequest, checks_green: bool) -> tuple[bool, str]:
        if request.action == WorkflowAction.MERGE_PR and request.require_green and not checks_green:
            return False, "Merge requires green verification."
        if not request.branch or request.branch == request.base:
            return False, "A non-default working branch is required."
        return True, "Workflow action is policy-approved."
