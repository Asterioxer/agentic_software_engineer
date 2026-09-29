from __future__ import annotations

from dataclasses import dataclass
from .domain import ToolCall

@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str

class ToolPolicy:
    ALLOWED_TOOLS = frozenset({
        "repository.inspect",
        "workspace.plan",
        "command.run",
        "verification.run",
    })

    def authorize(self, call: ToolCall) -> PolicyDecision:
        if call.tool not in self.ALLOWED_TOOLS:
            return PolicyDecision(False, f"Tool '{call.tool}' is not allowlisted.")
        return PolicyDecision(True, "Tool is explicitly allowlisted.")
