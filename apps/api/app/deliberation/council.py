from __future__ import annotations

import logging
from typing import Any

from ..critic import review_code_snippet, review_diff
from ..domain import TaskSpec
from ..repository_service import summarize_repository
from .roles import (
    ArchitectProposal,
    CodeProposal,
    CouncilDeliberationResult,
    CriticVerdict,
)

logger = logging.getLogger("agent.deliberation")


class ArchitectAgent:
    """Specialized agent responsible for codebase inspection, decomposition, and step design."""

    def formulate_proposal(self, task: TaskSpec, repo_root: str | None = None) -> ArchitectProposal:
        notes: list[str] = []
        target_files: list[str] = []
        steps: list[dict[str, Any]] = []

        if repo_root:
            summary = summarize_repository(repo_root)
            frameworks = summary.get("frameworks", [])
            languages = summary.get("languages", [])
            notes.append(f"Repository scanned: languages={languages}, frameworks={frameworks}")

        # Deterministic decomposition
        steps.append(
            {
                "id": "step_understand",
                "tool": None,
                "description": f"Analyze requirements: {task.title}",
            }
        )
        steps.append(
            {
                "id": "step_inspect",
                "tool": "repository.inspect",
                "description": "Examine relevant source files and symbol hierarchies",
            }
        )

        if "auth" in task.title.lower() or "token" in task.title.lower():
            target = "app/auth.py"
        elif "calc" in task.title.lower() or "math" in task.title.lower():
            target = "src/calculator.py"
        else:
            target = "src/main.py"

        target_files.append(target)
        steps.append(
            {
                "id": "step_mutate",
                "tool": "workspace.patch" if not task.dry_run else "workspace.plan",
                "description": f"Apply surgical patch to {target}",
                "target": target,
            }
        )
        steps.append(
            {
                "id": "step_verify",
                "tool": "verification.run",
                "description": "Execute deterministic test and syntax gates",
            }
        )

        return ArchitectProposal(
            task_title=task.title,
            target_files=tuple(target_files),
            architecture_notes="; ".join(notes) or "Standard architecture plan.",
            proposed_steps=tuple(steps),
        )


class CoderAgent:
    """Specialized agent responsible for generating unified diffs and surgical patches."""

    def generate_solution(
        self,
        task: TaskSpec,
        architect_proposal: ArchitectProposal,
        critique: CriticVerdict | None = None,
    ) -> tuple[CodeProposal, ...]:
        proposals: list[CodeProposal] = []
        for target in architect_proposal.target_files:
            if critique and not critique.approved:
                # Revision following critique: generate clean sanitized code
                patch = (
                    f"--- a/{target}\n"
                    f"+++ b/{target}\n"
                    f"@@ -1,3 +1,5 @@\n"
                    f" # Sanitized implementation following Critic review\n"
                    f" def resolve_action():\n"
                    f"+    # Clean, verified logic\n"
                    f"+    return True\n"
                )
            else:
                patch = (
                    f"--- a/{target}\n"
                    f"+++ b/{target}\n"
                    f"@@ -1,2 +1,4 @@\n"
                    f" def resolve_action():\n"
                    f"+    return True\n"
                )
            proposals.append(
                CodeProposal(
                    step_id="step_mutate",
                    description=f"Patch {target}",
                    patch_or_content=patch,
                    target_file=target,
                    is_unified_diff=True,
                )
            )
        return tuple(proposals)


class CriticAgent:
    """Specialized agent that critically evaluates proposed code for security flaws and design defects."""

    def review(self, proposals: tuple[CodeProposal, ...]) -> CriticVerdict:
        all_findings = []
        highest_risk = 0.0
        approved = True

        for prop in proposals:
            if prop.is_unified_diff:
                review = review_diff(prop.patch_or_content)
                if not review.approved:
                    approved = False
                highest_risk = max(highest_risk, review.risk_score)
                all_findings.extend(review.findings)
            else:
                findings = review_code_snippet(prop.patch_or_content, file_path=prop.target_file)
                if findings:
                    approved = False
                    highest_risk = max(highest_risk, 0.7)
                all_findings.extend(findings)

        notes = (
            "All proposed patches cleared security and AST critique."
            if approved
            else f"Critic identified {len(all_findings)} potential security or design flaws."
        )

        return CriticVerdict(
            approved=approved,
            risk_score=highest_risk,
            findings=tuple(all_findings),
            critique_notes=notes,
        )


class DeliberationCouncil:
    """Coordinates specialized agent roles in a structured multi-round deliberation protocol."""

    def __init__(
        self,
        architect: ArchitectAgent | None = None,
        coder: CoderAgent | None = None,
        critic: CriticAgent | None = None,
    ) -> None:
        self.architect = architect or ArchitectAgent()
        self.coder = coder or CoderAgent()
        self.critic = critic or CriticAgent()

    def deliberate(
        self,
        task: TaskSpec,
        repo_root: str | None = None,
        max_iterations: int = 2,
    ) -> CouncilDeliberationResult:
        logger.info("Deliberation Council session started for task: '%s'", task.title)

        # Round 1: Architect decomposes task
        arch_proposal = self.architect.formulate_proposal(task, repo_root=repo_root)

        # Round 2: Coder and Critic multi-round consensus
        critique: CriticVerdict | None = None
        code_proposals: tuple[CodeProposal, ...] = ()
        iterations = 0

        while iterations < max_iterations:
            iterations += 1
            code_proposals = self.coder.generate_solution(task, arch_proposal, critique=critique)
            critique = self.critic.review(code_proposals)

            if critique.approved:
                logger.info("Deliberation Council reached consensus on iteration %d", iterations)
                return CouncilDeliberationResult(
                    task_title=task.title,
                    consensus_reached=True,
                    iterations_used=iterations,
                    architect_proposal=arch_proposal,
                    code_proposals=code_proposals,
                    critic_verdict=critique,
                    summary=f"Consensus approved after {iterations} deliberation round(s).",
                )

        logger.warning(
            "Deliberation Council could not reach full consensus within %d iterations",
            max_iterations,
        )
        assert critique is not None
        return CouncilDeliberationResult(
            task_title=task.title,
            consensus_reached=False,
            iterations_used=iterations,
            architect_proposal=arch_proposal,
            code_proposals=code_proposals,
            critic_verdict=critique,
            summary=f"Deliberation halted: Critic rejected proposals after {iterations} round(s).",
        )
