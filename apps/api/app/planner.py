from __future__ import annotations

from .domain import PlanStep, TaskSpec


def build_deterministic_plan(task: TaskSpec) -> list[PlanStep]:
    return [
        PlanStep(
            id="understand",
            description=f"Normalize task intent: {task.title}",
            success_criteria=["Task has a concrete title and non-empty description."],
        ),
        PlanStep(
            id="inspect",
            description="Inspect the target repository and identify relevant components.",
            tool="repository.inspect",
            success_criteria=["Repository metadata is available or an explicit repository is absent."],
        ),
        PlanStep(
            id="implement",
            description="Represent the smallest necessary implementation change.",
            tool="workspace.plan",
            success_criteria=["Planned actions are bounded and tied to the task."],
        ),
        PlanStep(
            id="verify",
            description="Run independent verification against the declared success criteria.",
            tool="verification.run",
            success_criteria=["All mandatory verification checks pass."],
        ),
    ]
