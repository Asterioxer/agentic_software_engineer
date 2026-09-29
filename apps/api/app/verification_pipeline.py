from __future__ import annotations

from dataclasses import dataclass
from .command_runner import CommandRunner
from .domain import VerificationResult

@dataclass(frozen=True)
class VerificationEvidence:
    checks: list[VerificationResult]
    passed: bool

def run_verification(root: str, expected_files: list[str] | None = None) -> VerificationEvidence:
    runner = CommandRunner(root)
    checks: list[VerificationResult] = []
    from .verification import verify_workspace
    checks.extend(verify_workspace(root, expected_files or []))
    result = runner.run("git.diff.check")
    checks.append(VerificationResult(
        check="command:git.diff.check",
        passed=result.exit_code == 0 and not result.timed_out,
        detail="Git diff has no whitespace errors." if result.exit_code == 0 and not result.timed_out else
        f"git diff check failed: exit_code={result.exit_code} timed_out={result.timed_out} stderr={result.stderr[-500:]}",
    ))
    return VerificationEvidence(checks=checks, passed=all(x.passed for x in checks))
