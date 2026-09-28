from __future__ import annotations
from .domain import PlanStep, TaskSpec

def build_deterministic_plan(task: TaskSpec, repository_summary: dict[str, object] | None = None) -> list[PlanStep]:
    steps=[PlanStep(id="understand",description=f"Normalize task intent: {task.title}",success_criteria=["Concrete task intent exists."])]
    if task.repository:
        count=repository_summary.get("file_count",0) if repository_summary else 0
        steps.append(PlanStep(id="inspect",description=f"Inspect repository context ({count} indexed files).",tool="repository.inspect",success_criteria=["Repository context is bounded and available."]))
    steps.extend([PlanStep(id="implement",description="Plan the smallest necessary implementation change.",tool="workspace.plan",success_criteria=["Actions are explicit and bounded."]),PlanStep(id="verify",description="Run independent verification.",tool="verification.run",success_criteria=["Mandatory checks pass."])])
    return steps

def plan_with_repository(task: TaskSpec) -> tuple[list[PlanStep],dict[str,object]|None]:
    if not task.repository:return build_deterministic_plan(task),None
    from .repository_service import summarize_repository
    summary=summarize_repository(task.repository)
    return build_deterministic_plan(task,summary),summary
