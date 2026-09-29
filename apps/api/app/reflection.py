from __future__ import annotations

from dataclasses import dataclass
from .domain import VerificationResult

@dataclass(frozen=True)
class Reflection:
    passed: bool
    diagnosis: str
    next_action: str
    retry_budget: int

def reflect(results: list[VerificationResult], retry_budget: int = 2) -> Reflection:
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
