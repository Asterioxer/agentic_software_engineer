from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .critic import review_diff
from .domain import FailureCategory
from .llm.repair import repair_code

logger = logging.getLogger("agent.self_correction")


@dataclass
class StrategyAttempt:
    strategy_id: str
    failure_signature: str
    category: str
    target_file: str | None
    proposed_fix_hash: str
    attempt_number: int
    timestamp: str


@dataclass
class CorrectionPlan:
    category: FailureCategory
    target_file: str | None
    explanation: str
    proposed_code: str | None
    risk_score: float
    approved: bool
    is_loop: bool = False
    rejection_reason: str | None = None


class SelfCorrectionEngine:
    """Disciplined autonomous debugging, failure classification, and repair loop.

    Enforces:
    - Multi-category failure classification (syntax, dependency, test, type, runtime, regression)
    - Anti-cycling detection: prevents repeating identical failed repair strategies
    - Security critic gating on all proposed code corrections
    - Bounded retry tracking
    """

    def __init__(self, max_strategy_repeats: int = 1) -> None:
        self.max_strategy_repeats = max_strategy_repeats
        self._history: list[StrategyAttempt] = []

    @staticmethod
    def compute_failure_signature(
        category: str, check_or_msg: str, target_file: str | None = None
    ) -> str:
        """Deterministic fingerprint of a failure."""
        normalized = (
            f"{category.strip().lower()}::{check_or_msg.strip().lower()}::{target_file or 'none'}"
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def is_cycling(self, failure_signature: str, proposed_fix: str) -> bool:
        """Detect whether this exact repair fix has already been attempted for this failure signature."""
        fix_hash = hashlib.sha256(proposed_fix.encode("utf-8")).hexdigest()[:16]
        matches = [
            att
            for att in self._history
            if att.failure_signature == failure_signature and att.proposed_fix_hash == fix_hash
        ]
        return len(matches) >= self.max_strategy_repeats

    def record_attempt(
        self,
        failure_signature: str,
        category: str,
        target_file: str | None,
        proposed_fix: str,
    ) -> StrategyAttempt:
        fix_hash = hashlib.sha256(proposed_fix.encode("utf-8")).hexdigest()[:16]
        prior_count = sum(1 for att in self._history if att.failure_signature == failure_signature)
        attempt = StrategyAttempt(
            strategy_id=f"strat_{len(self._history) + 1}",
            failure_signature=failure_signature,
            category=category,
            target_file=target_file,
            proposed_fix_hash=fix_hash,
            attempt_number=prior_count + 1,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._history.append(attempt)
        return attempt

    def classify_detailed_failure(
        self, error_message: str, check_name: str = ""
    ) -> FailureCategory:
        """Classify failure into specific operational failure categories."""
        msg = f"{check_name} {error_message}".lower()

        if "syntaxerror" in msg or "invalid syntax" in msg or "syntax:" in msg:
            return FailureCategory.SYNTAX_ERROR
        if "modulenotfounderror" in msg or "no module named" in msg or "importerror" in msg:
            return FailureCategory.DEPENDENCY_MISSING
        if "policy violation" in msg or "not allowlisted" in msg or "forbidden" in msg:
            return FailureCategory.POLICY_VIOLATION
        if (
            "approval invalidated" in msg
            or "fingerprint mismatch" in msg
            or "approval mismatch" in msg
        ):
            return FailureCategory.APPROVAL_INVALIDATED
        if "strategy loop" in msg or "cycling detected" in msg:
            return FailureCategory.STRATEGY_LOOP
        if "cancelled" in msg:
            return FailureCategory.CANCELLED
        if "timed out" in msg or "timeout" in msg:
            return FailureCategory.TIMEOUT
        if "assertionerror" in msg or "failed test" in msg or "proof_of_test" in msg:
            return FailureCategory.VALIDATION_FAILURE
        return FailureCategory.EXECUTION_ERROR

    def generate_corrective_plan(
        self,
        failing_check: str,
        error_detail: str,
        workspace_root: str | Path | None = None,
    ) -> CorrectionPlan:
        """Diagnose failure, extract target file, synthesize repair, check for loops and security."""
        category = self.classify_detailed_failure(error_detail, failing_check)

        # Extract target file from check name (e.g. 'syntax:main.py', 'file:test_api.py')
        target_file: str | None = None
        if ":" in failing_check:
            parts = failing_check.split(":", 1)
            target_file = parts[1].strip()

        if not target_file and workspace_root:
            # Heuristic match for filenames in error detail
            match = re.search(r"([\w/-]+\.(?:py|json|toml|ts|tsx|js))", error_detail)
            if match:
                target_file = match.group(1)

        failure_sig = self.compute_failure_signature(category.value, error_detail, target_file)

        # If missing target file or unrepairable category, exit early
        if not target_file or not workspace_root:
            return CorrectionPlan(
                category=category,
                target_file=target_file,
                explanation=f"Cannot autonomously repair: {error_detail}",
                proposed_code=None,
                risk_score=0.0,
                approved=False,
                is_loop=False,
                rejection_reason="No target source file could be resolved for autonomous repair.",
            )

        root_path = Path(workspace_root).resolve()
        target_path = (root_path / target_file).resolve()
        if not target_path.exists() or not target_path.is_file():
            return CorrectionPlan(
                category=category,
                target_file=target_file,
                explanation=f"Target file '{target_file}' not found in workspace.",
                proposed_code=None,
                risk_score=0.0,
                approved=False,
                is_loop=False,
                rejection_reason=f"Target file '{target_file}' does not exist on disk.",
            )

        try:
            original_code = target_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return CorrectionPlan(
                category=category,
                target_file=target_file,
                explanation=f"Failed to read target file: {exc}",
                proposed_code=None,
                risk_score=0.0,
                approved=False,
                is_loop=False,
                rejection_reason=str(exc),
            )

        # Synthesize repair using bounded repair_code
        repair_res = repair_code(
            broken_code=original_code,
            error_message=error_detail,
        )

        proposed_code = repair_res.repaired_code

        # Check for Strategy Looping (Anti-Cycling)
        if self.is_cycling(failure_sig, proposed_code):
            logger.warning(
                "Strategy loop detected for failure %s on %s. Refusing to repeat identical repair.",
                failure_sig,
                target_file,
            )
            return CorrectionPlan(
                category=FailureCategory.STRATEGY_LOOP,
                target_file=target_file,
                explanation="Strategy loop detected: agent attempted the exact same code repair strategy repeatedly.",
                proposed_code=None,
                risk_score=0.0,
                approved=False,
                is_loop=True,
                rejection_reason="Anti-cycling safety gate blocked identical repeated repair strategy.",
            )

        # Record this strategy attempt
        self.record_attempt(failure_sig, category.value, target_file, proposed_code)

        # Security Critic Review of proposed change
        # Create synthetic diff with added lines prefixed by +
        diff_lines = "\n".join(f"+{line}" for line in proposed_code.splitlines())
        diff_text = f"--- a/{target_file}\n+++ b/{target_file}\n@@ -0,0 +1,{len(proposed_code.splitlines())} @@\n{diff_lines}\n"
        review = review_diff(diff_text)

        if not review.approved:
            logger.warning(
                "Security critic rejected proposed self-correction for %s (risk: %.1f): %s",
                target_file,
                review.risk_score,
                review.summary,
            )
            return CorrectionPlan(
                category=category,
                target_file=target_file,
                explanation=f"Proposed fix rejected by Security Critic: {review.summary}",
                proposed_code=proposed_code,
                risk_score=review.risk_score,
                approved=False,
                is_loop=False,
                rejection_reason=f"Security Critic rejection (risk: {review.risk_score})",
            )

        return CorrectionPlan(
            category=category,
            target_file=target_file,
            explanation=repair_res.explanation,
            proposed_code=proposed_code,
            risk_score=review.risk_score,
            approved=True,
            is_loop=False,
        )
