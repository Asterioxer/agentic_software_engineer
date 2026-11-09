from __future__ import annotations

import ast
import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from .domain import VerificationResult


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def verify_syntax(target: Path, step_id: str | None = None) -> VerificationResult | None:
    """Validate language syntax for supported structured file formats."""
    suffix = target.suffix.lower()
    ts = _utc_now_iso()
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return VerificationResult(
            check=f"encoding:{target.name}",
            passed=False,
            detail=f"File {target.name} is not valid UTF-8 text.",
            step_id=step_id,
            category="syntax",
            expected="UTF-8 encoded text",
            actual="UnicodeDecodeError",
            timestamp=ts,
        )
    except OSError as exc:
        return VerificationResult(
            check=f"read:{target.name}",
            passed=False,
            detail=f"Failed to read {target.name}: {exc}",
            step_id=step_id,
            category="filesystem",
            expected="Readable file",
            actual=str(exc),
            timestamp=ts,
        )

    if suffix == ".py":
        try:
            ast.parse(content, filename=str(target))
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=True,
                detail=f"Python AST syntax validation passed for {target.name}.",
                step_id=step_id,
                category="syntax",
                expected="Valid Python syntax",
                actual="AST parsed successfully",
                timestamp=ts,
            )
        except SyntaxError as exc:
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=False,
                detail=f"Syntax error in {target.name} (line {exc.lineno}): {exc.msg}",
                step_id=step_id,
                category="syntax",
                expected="Valid Python syntax",
                actual=f"SyntaxError at line {exc.lineno}: {exc.msg}",
                timestamp=ts,
            )

    if suffix == ".json":
        try:
            json.loads(content)
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=True,
                detail=f"JSON syntax validation passed for {target.name}.",
                step_id=step_id,
                category="syntax",
                expected="Valid JSON syntax",
                actual="JSON decoded successfully",
                timestamp=ts,
            )
        except json.JSONDecodeError as exc:
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=False,
                detail=f"JSON decode error in {target.name} (line {exc.lineno}): {exc.msg}",
                step_id=step_id,
                category="syntax",
                expected="Valid JSON syntax",
                actual=f"JSONDecodeError at line {exc.lineno}: {exc.msg}",
                timestamp=ts,
            )

    if suffix == ".toml":
        try:
            tomllib.loads(content)
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=True,
                detail=f"TOML syntax validation passed for {target.name}.",
                step_id=step_id,
                category="syntax",
                expected="Valid TOML syntax",
                actual="TOML decoded successfully",
                timestamp=ts,
            )
        except tomllib.TOMLDecodeError as exc:
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=False,
                detail=f"TOML decode error in {target.name}: {exc}",
                step_id=step_id,
                category="syntax",
                expected="Valid TOML syntax",
                actual=f"TOMLDecodeError: {exc}",
                timestamp=ts,
            )

    return None


def verify_proof_of_test(target: Path, step_id: str | None = None) -> VerificationResult | None:
    """Verify that a test file contains actual, executable test definitions."""
    name = target.name.lower()
    ts = _utc_now_iso()
    if not (name.startswith("test_") or name.endswith("_test.py")):
        return None

    try:
        content = target.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(target))
    except (SyntaxError, OSError, ValueError):
        # Syntax issues will be caught by verify_syntax
        return None

    test_count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ) or (isinstance(node, ast.ClassDef) and node.name.startswith("Test")):
            test_count += 1

    if test_count == 0:
        return VerificationResult(
            check=f"proof_of_test:{target.name}",
            passed=False,
            detail=f"Test file {target.name} contains no test definitions (test_* functions or Test* classes).",
            step_id=step_id,
            category="tests",
            expected=">=1 executable test function",
            actual="0 test definitions found",
            timestamp=ts,
        )

    return VerificationResult(
        check=f"proof_of_test:{target.name}",
        passed=True,
        detail=f"Test file {target.name} contains {test_count} verified test definition(s).",
        step_id=step_id,
        category="tests",
        expected=">=1 executable test function",
        actual=f"{test_count} test definition(s) discovered",
        timestamp=ts,
    )


def verify_security_critic(target: Path, step_id: str | None = None) -> VerificationResult | None:
    """Run automated security critic rules against code files."""
    if target.suffix.lower() not in (".py", ".js", ".ts", ".tsx", ".jsx"):
        return None

    ts = _utc_now_iso()
    from .critic import review_code_snippet

    try:
        content = target.read_text(encoding="utf-8")
        findings = review_code_snippet(content, file_path=target.name)
    except (OSError, ValueError):
        return None

    critical_or_high = [f for f in findings if f.severity in ("CRITICAL", "HIGH")]
    if critical_or_high:
        reasons = "; ".join(f"[{f.rule_id}] {f.description}" for f in critical_or_high[:2])
        return VerificationResult(
            check=f"security_critic:{target.name}",
            passed=False,
            detail=f"Security critic rejected {target.name}: {reasons}",
            step_id=step_id,
            category="security",
            expected="0 critical or high security findings",
            actual=f"{len(critical_or_high)} security issue(s) detected",
            timestamp=ts,
        )
    return VerificationResult(
        check=f"security_critic:{target.name}",
        passed=True,
        detail=f"Security critic passed for {target.name}.",
        step_id=step_id,
        category="security",
        expected="0 critical or high security findings",
        actual="Clean (0 security violations)",
        timestamp=ts,
    )


def verify_workspace(
    root: str, expected_files: list[str], step_id: str | None = None
) -> list[VerificationResult]:
    """Execute multi-stage workspace verification: existence, boundary, syntax, proof-of-test, and security."""
    base = Path(root).resolve()
    results: list[VerificationResult] = []
    ts = _utc_now_iso()

    for relative in expected_files:
        target = (base / relative).resolve()
        safe = target == base or base in target.parents

        if not safe:
            results.append(
                VerificationResult(
                    check=f"file:{relative}",
                    passed=False,
                    detail=f"Expected file '{relative}' escapes the workspace root boundary.",
                    step_id=step_id,
                    category="filesystem",
                    expected="File within workspace boundary",
                    actual="Escapes workspace root",
                    timestamp=ts,
                )
            )
            continue

        if not target.exists():
            results.append(
                VerificationResult(
                    check=f"file:{relative}",
                    passed=False,
                    detail=f"Expected file '{relative}' is missing from the workspace.",
                    step_id=step_id,
                    category="filesystem",
                    expected="File exists in workspace",
                    actual="File absent",
                    timestamp=ts,
                )
            )
            continue

        results.append(
            VerificationResult(
                check=f"file:{relative}",
                passed=True,
                detail=f"Expected file '{relative}' exists inside workspace.",
                step_id=step_id,
                category="filesystem",
                expected="File exists in workspace",
                actual="File confirmed on disk",
                timestamp=ts,
            )
        )

        if target.is_file():
            syntax_check = verify_syntax(target, step_id=step_id)
            if syntax_check:
                results.append(syntax_check)

            test_check = verify_proof_of_test(target, step_id=step_id)
            if test_check:
                results.append(test_check)

            critic_check = verify_security_critic(target, step_id=step_id)
            if critic_check:
                results.append(critic_check)

    return results
