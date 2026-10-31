from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .domain import ToolCall


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    risk_level: str = "low"
    requires_approval: bool = False


class ToolPolicy:
    ALLOWED_TOOLS: ClassVar[frozenset[str]] = frozenset(
        {
            "repository.inspect",
            "workspace.plan",
            "command.run",
            "verification.run",
        }
    )

    def classify_risk(self, call: ToolCall) -> str:
        if call.tool == "workspace.plan":
            if not bool(call.arguments.get("dry_run", True)):
                return "high"
            return "low"
        if call.tool == "command.run":
            return "medium"
        return "low"

    def requires_operator_approval(self, call: ToolCall) -> bool:
        return self.classify_risk(call) == "high"

    def authorize(self, call: ToolCall) -> PolicyDecision:
        if call.tool not in self.ALLOWED_TOOLS:
            return PolicyDecision(
                False, f"Tool '{call.tool}' is not allowlisted.", risk_level="high"
            )

        risk = self.classify_risk(call)
        needs_approval = self.requires_operator_approval(call)

        return PolicyDecision(
            allowed=True,
            reason="Tool is explicitly allowlisted.",
            risk_level=risk,
            requires_approval=needs_approval,
        )
