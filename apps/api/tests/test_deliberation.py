from __future__ import annotations

from pathlib import Path

from app.deliberation import (
    ArchitectAgent,
    ArchitectProposal,
    CodeProposal,
    CoderAgent,
    CriticAgent,
    CriticVerdict,
    DeliberationCouncil,
)
from app.domain import TaskSpec


def test_architect_agent_decomposition(tmp_path: Path) -> None:
    architect = ArchitectAgent()
    task = TaskSpec(
        title="Implement token revocation in auth",
        description="Add token blacklist to prevent replay",
        repository=str(tmp_path),
    )
    proposal = architect.formulate_proposal(task, repo_root=str(tmp_path))
    assert proposal.task_title == task.title
    assert "app/auth.py" in proposal.target_files
    assert len(proposal.proposed_steps) == 4
    step_ids = [s["id"] for s in proposal.proposed_steps]
    assert "step_understand" in step_ids
    assert "step_inspect" in step_ids
    assert "step_mutate" in step_ids
    assert "step_verify" in step_ids


def test_coder_and_critic_consensus() -> None:
    architect = ArchitectAgent()
    coder = CoderAgent()
    critic = CriticAgent()

    task = TaskSpec(
        title="Add math divide method",
        description="Safe division operation",
    )
    arch_prop = architect.formulate_proposal(task)
    code_proposals = coder.generate_solution(task, arch_prop)
    assert len(code_proposals) > 0
    assert code_proposals[0].is_unified_diff

    verdict = critic.review(code_proposals)
    assert verdict.approved
    assert verdict.risk_score == 0.0


def test_critic_rejects_vulnerable_proposal() -> None:
    critic = CriticAgent()
    vuln_patch = (
        "--- a/app/server.py\n"
        "+++ b/app/server.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def handle(query):\n"
        "+    API_KEY = 'AKIA1111111111111111'\n"
        "+    return eval(query)\n"
    )
    proposal = CodeProposal(
        step_id="step_1",
        description="Add handler",
        patch_or_content=vuln_patch,
        target_file="app/server.py",
        is_unified_diff=True,
    )
    verdict = critic.review((proposal,))
    assert not verdict.approved
    assert verdict.risk_score >= 0.5
    assert any(f.rule_id == "SEC-001" for f in verdict.findings)


def test_deliberation_council_clean_consensus(tmp_path: Path) -> None:
    council = DeliberationCouncil()
    task = TaskSpec(
        title="Implement matrix multiply",
        description="Safe numerical multiplication",
        repository=str(tmp_path),
    )
    result = council.deliberate(task, repo_root=str(tmp_path))
    assert result.consensus_reached
    assert result.iterations_used == 1
    assert result.critic_verdict.approved
    assert "Consensus approved" in result.summary


def test_deliberation_council_rejection_on_unresolvable_critic() -> None:
    class StubbornMaliciousCoder(CoderAgent):
        def generate_solution(
            self,
            task: TaskSpec,
            architect_proposal: ArchitectProposal,
            critique: CriticVerdict | None = None,
        ) -> tuple[CodeProposal, ...]:
            return (
                CodeProposal(
                    step_id="step_1",
                    description="Malicious",
                    patch_or_content=(
                        "--- a/bad.py\n+++ b/bad.py\n@@ -1,1 +1,2 @@\n+SECRET = 'AKIA1111111111111111'\n"
                    ),
                    target_file="bad.py",
                    is_unified_diff=True,
                ),
            )

    council = DeliberationCouncil(coder=StubbornMaliciousCoder())
    task = TaskSpec(
        title="Attempt unresolvable security flaw",
        description="Testing rejection handling",
    )
    result = council.deliberate(task, max_iterations=2)
    assert not result.consensus_reached
    assert result.iterations_used == 2
    assert not result.critic_verdict.approved
    assert "Critic rejected" in result.summary
