from __future__ import annotations

from .domain import (
    RunEvent,
    RunStatus,
    TaskSpec,
    ToolCall,
    VerificationResult,
)
from .planner import build_deterministic_plan
from .policy import ToolPolicy
from .tools import ToolRegistry


class AgentRun:
    def __init__(self, task: TaskSpec, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self.task = task
        self.registry = registry
        self.policy = policy
        self.events: list[RunEvent] = []

    def _emit(self, status: RunStatus, message: str) -> None:
        self.events.append(RunEvent(sequence=len(self.events) + 1, status=status, message=message))

    def execute(self) -> dict[str, object]:
        self._emit(RunStatus.INTAKE, "Task accepted.")
        plan = build_deterministic_plan(self.task)
        self._emit(RunStatus.PLANNING, f"Built bounded plan with {len(plan)} steps.")

        self._emit(RunStatus.EXECUTING, "Executing declared tools.")
        for step in plan:
            if step.tool is None:
                continue
            call = ToolCall(tool=step.tool, arguments={"repository": self.task.repository})
            decision = self.policy.authorize(call)
            if not decision.allowed:
                self._emit(RunStatus.FAILED, decision.reason)
                return {"status": RunStatus.FAILED.value, "plan": plan, "events": self.events}
            self.registry.get(step.tool).handler(call.arguments)

        self._emit(RunStatus.VERIFYING, "Running independent deterministic checks.")
        results = [
            VerificationResult(
                check="plan_exists",
                passed=bool(plan),
                detail="A non-empty plan was produced.",
            ),
            VerificationResult(
                check="tool_allowlist",
                passed=all(
                    step.tool is None
                    or self.policy.authorize(ToolCall(tool=step.tool, arguments={})).allowed
                    for step in plan
                ),
                detail="All declared tools are policy-approved.",
            ),
        ]
        failed = [result for result in results if not result.passed]
        if failed:
            self._emit(RunStatus.FAILED, f"{len(failed)} verification check(s) failed.")
            return {"status": RunStatus.FAILED.value, "plan": plan, "events": self.events}

        self._emit(RunStatus.REFLECTING, "Summarizing execution evidence.")
        self._emit(RunStatus.COMPLETED, "Run completed with verification evidence.")
        return {
            "status": RunStatus.COMPLETED.value,
            "plan": plan,
            "verification": results,
            "events": self.events,
        }
