from __future__ import annotations

from dataclasses import dataclass

from .execution import WorkspaceAction


@dataclass(frozen=True)
class ExecutionDecision:
    allowed: bool
    reason: str


class ExecutionPolicy:
    MAX_ACTIONS = 20
    ALLOWED_KINDS = frozenset({"write", "delete"})

    def authorize(self, actions: list[WorkspaceAction]) -> ExecutionDecision:
        if len(actions) > self.MAX_ACTIONS:
            return ExecutionDecision(False, f"Action limit exceeded: {len(actions)} > {self.MAX_ACTIONS}.")
        for action in actions:
            if action.kind not in self.ALLOWED_KINDS:
                return ExecutionDecision(False, f"Action kind '{action.kind}' is not permitted.")
        return ExecutionDecision(True, "Workspace actions are policy-approved.")
