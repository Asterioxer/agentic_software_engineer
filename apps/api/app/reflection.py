from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import FailureCategory, FailureDiagnosis, VerificationResult


@dataclass(frozen=True)
class Reflection:
    passed: bool
    diagnosis: str
    next_action: str
    retry_budget: int


def classify_failure(
    error_text: str,
    step_output: dict[str, Any] | None = None,
    verification_results: list[VerificationResult] | None = None,
) -> FailureDiagnosis:
    """Classify execution and verification failures into actionable failure categories."""
    combined = error_text
    if step_output:
        combined += f" {step_output.get('stderr', '')} {step_output.get('detail', '')}"
    if verification_results:
        combined += " " + " ".join(v.detail for v in verification_results if not v.passed)

    lower = combined.lower()

    if any(
        k in lower
        for k in ("not allowlisted", "escapes the configured", "not permitted", "unauthorized")
    ):
        return FailureDiagnosis(
            category=FailureCategory.POLICY_VIOLATION,
            message="Operation rejected by security policy.",
            recoverable=False,
            suggested_recovery="Terminate run: requested action violates execution boundary.",
        )

    if any(k in lower for k in ("timed out", "timeoutexpired", "timeout")):
        return FailureDiagnosis(
            category=FailureCategory.TIMEOUT,
            message="Command execution timed out.",
            recoverable=True,
            suggested_recovery="Retry with scoped arguments or narrower target.",
        )

    if any(k in lower for k in ("syntaxerror", "indentationerror", "invalid syntax")):
        return FailureDiagnosis(
            category=FailureCategory.SYNTAX_ERROR,
            message="Code syntax or indentation error detected.",
            recoverable=True,
            suggested_recovery="Re-plan patch to fix syntax and indentation.",
        )

    if any(k in lower for k in ("modulenotfounderror", "importerror", "no module named")):
        return FailureDiagnosis(
            category=FailureCategory.DEPENDENCY_MISSING,
            message="Required dependency or module is missing from the environment.",
            recoverable=False,
            suggested_recovery="Admit failure: missing host dependency cannot be installed without elevation.",
        )

    if (
        (verification_results and any(not v.passed for v in verification_results))
        or "failed:" in lower
        or "assertionerror" in lower
    ):
        return FailureDiagnosis(
            category=FailureCategory.VALIDATION_FAILURE,
            message="Verification gates or test assertions failed.",
            recoverable=True,
            suggested_recovery="Re-plan only the failing boundary without expanding mutation scope.",
        )

    return FailureDiagnosis(
        category=FailureCategory.EXECUTION_ERROR,
        message=f"Execution error: {error_text[:200]}",
        recoverable=True,
        suggested_recovery="Inspect workspace state and retry bounded operation.",
    )


def reflect(results: list[VerificationResult], retry_budget: int = 2) -> Reflection:
    """Evaluate verification results and generate bounded reflection guidance."""
    failures = [item for item in results if not item.passed]
    if not failures:
        return Reflection(True, "All verification gates passed.", "Complete run.", 0)
    names = ", ".join(item.check for item in failures[:5])
    return Reflection(
        False,
        f"Verification failures detected: {names}.",
        "Re-plan only the failed boundary; do not broaden the mutation scope.",
        max(0, retry_budget),
    )
