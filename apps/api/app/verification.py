from __future__ import annotations

from pathlib import Path

from .domain import VerificationResult


def verify_workspace(root: str, expected_files: list[str]) -> list[VerificationResult]:
    base = Path(root).resolve()
    results: list[VerificationResult] = []
    for relative in expected_files:
        target = (base / relative).resolve()
        safe = target == base or base in target.parents
        results.append(
            VerificationResult(
                check=f"file:{relative}",
                passed=safe and target.exists(),
                detail="Expected file exists inside the workspace."
                if safe and target.exists()
                else "Expected file is missing or outside the workspace.",
            )
        )
    return results
