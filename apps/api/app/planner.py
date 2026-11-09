from __future__ import annotations

from typing import Any

from .domain import PlanStep, StepStatus, TaskSpec


def build_deterministic_plan(
    task: TaskSpec, repository_summary: dict[str, Any] | None = None
) -> list[PlanStep]:
    """Construct an inspectable, typed execution plan with explicit inputs and criteria."""
    steps: list[PlanStep] = [
        PlanStep(
            id="understand",
            description=f"Normalize task intent: {task.title}",
            tool=None,
            inputs={
                "title": task.title,
                "description": task.description,
                "constraints": task.constraints,
            },
            expected_outputs=["normalized_intent", "task_scope"],
            validation_criteria=["Task title and description are bounded and validated."],
            success_criteria=["Concrete task intent exists."],
            depends_on=[],
            preconditions=["task_title_valid", "task_description_valid"],
            postconditions=["normalized_intent_available"],
            status=StepStatus.PENDING,
            requires_approval=False,
        )
    ]

    last_step_id = "understand"

    if task.repository:
        count = repository_summary.get("file_count", 0) if repository_summary else 0
        steps.append(
            PlanStep(
                id="inspect",
                description=f"Inspect repository context ({count} indexed files).",
                tool="repository.inspect",
                inputs={"repository": task.repository, "query": task.title},
                expected_outputs=["repository_metadata", "relevant_snippets", "languages"],
                validation_criteria=["Repository context is bounded and accessible."],
                success_criteria=["Repository context is bounded and available."],
                depends_on=[last_step_id],
                preconditions=["workspace_directory_exists"],
                postconditions=["repository_summary_available"],
                status=StepStatus.PENDING,
                requires_approval=False,
            )
        )
        last_step_id = "inspect"

    # Mutation step
    is_real_mutation = not task.dry_run
    steps.append(
        PlanStep(
            id="implement",
            description="Execute bounded workspace mutation or dry-run plan.",
            tool="workspace.plan",
            inputs={
                "repository": task.repository,
                "dry_run": task.dry_run,
                "kind": "write",
                "path": "agent-plan.txt",
                "content": f"# Plan: {task.title}\n\n{task.description}\n",
            },
            expected_outputs=["action_result", "mutation_status"],
            validation_criteria=[
                "Action paths stay within workspace boundary.",
                "Action kind is allowlisted.",
            ],
            success_criteria=["Actions are explicit and bounded."],
            depends_on=[last_step_id],
            preconditions=["workspace_directory_exists", "approval_granted_if_required"],
            postconditions=["mutation_applied_or_previewed", "checksum_verified"],
            status=StepStatus.PENDING,
            requires_approval=is_real_mutation and not task.auto_approve,
        )
    )

    # Independent verification step
    steps.append(
        PlanStep(
            id="verify",
            description="Run independent deterministic checks.",
            tool="verification.run",
            inputs={"repository": task.repository, "expected_files": list(task.expected_files)},
            expected_outputs=["verification_evidence", "gate_status"],
            validation_criteria=["All verification gates evaluate to true."],
            success_criteria=["Mandatory checks pass."],
            depends_on=["implement"],
            preconditions=["implementation_step_completed"],
            postconditions=["independent_verification_passed"],
            status=StepStatus.PENDING,
            requires_approval=False,
        )
    )

    return steps


def plan_with_repository(task: TaskSpec) -> tuple[list[PlanStep], dict[str, Any] | None]:
    if not task.repository:
        return build_deterministic_plan(task), None
    from .repository_service import summarize_repository

    summary = summarize_repository(task.repository)
    return build_deterministic_plan(task, summary), summary
