from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .command_runner import CommandRunner
from .domain import VerificationResult

@dataclass(frozen=True)
class VerificationEvidence:
    checks: list[VerificationResult]
    passed: bool

def run_verification(root: str, expected_files: list[str] | None = None) -> VerificationEvidence:
    checks: list[VerificationResult] = []
    from .verification import verify_workspace
    checks.extend(verify_workspace(root, expected_files or []))
    base = Path(root).resolve()
    if (base / ".git").exists():
        result = CommandRunner(str(base)).run("git.diff.check")
        passed = result.exit_code == 0 and not result.timed_out
        checks.append(VerificationResult(
            check="command:git.diff.check",
            passed=passed,
            detail="Git diff has no whitespace errors." if passed else
            f"git diff check failed: exit_code={result.exit_code} timed_out={result.timed_out} stderr={result.stderr[-500:]}",
        ))
    else:
        checks.append(VerificationResult(
            check="command:git.diff.check",
            passed=True,
            detail="Skipped because the workspace is not a Git checkout.",
        ))
    return VerificationEvidence(checks=checks, passed=all(check.passed for check in checks))
