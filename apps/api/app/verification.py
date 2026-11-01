from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

from .domain import VerificationResult


def verify_syntax(target: Path) -> VerificationResult | None:
    """Validate language syntax for supported structured file formats."""
    suffix = target.suffix.lower()
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return VerificationResult(
            check=f"encoding:{target.name}",
            passed=False,
            detail=f"File {target.name} is not valid UTF-8 text.",
        )
    except OSError as exc:
        return VerificationResult(
            check=f"read:{target.name}",
            passed=False,
            detail=f"Failed to read {target.name}: {exc}",
        )

    if suffix == ".py":
        try:
            ast.parse(content, filename=str(target))
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=True,
                detail=f"Python AST syntax validation passed for {target.name}.",
            )
        except SyntaxError as exc:
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=False,
                detail=f"Syntax error in {target.name} (line {exc.lineno}): {exc.msg}",
            )

    if suffix == ".json":
        try:
            json.loads(content)
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=True,
                detail=f"JSON syntax validation passed for {target.name}.",
            )
        except json.JSONDecodeError as exc:
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=False,
                detail=f"JSON decode error in {target.name} (line {exc.lineno}): {exc.msg}",
            )

    if suffix == ".toml":
        try:
            tomllib.loads(content)
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=True,
                detail=f"TOML syntax validation passed for {target.name}.",
            )
        except tomllib.TOMLDecodeError as exc:
            return VerificationResult(
                check=f"syntax:{target.name}",
                passed=False,
                detail=f"TOML decode error in {target.name}: {exc}",
            )

    return None


def verify_proof_of_test(target: Path) -> VerificationResult | None:
    """Verify that a test file contains actual, executable test definitions."""
    name = target.name.lower()
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
        )

    return VerificationResult(
        check=f"proof_of_test:{target.name}",
        passed=True,
        detail=f"Test file {target.name} contains {test_count} verified test definition(s).",
    )


def verify_security_critic(target: Path) -> VerificationResult | None:
    """Run automated security critic rules against code files."""
    if target.suffix.lower() not in (".py", ".js", ".ts", ".tsx", ".jsx"):
        return None

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
        )
    return VerificationResult(
        check=f"security_critic:{target.name}",
        passed=True,
        detail=f"Security critic passed for {target.name}.",
    )


def verify_workspace(root: str, expected_files: list[str]) -> list[VerificationResult]:
    """Execute multi-stage workspace verification: existence, boundary, syntax, proof-of-test, and security."""
    base = Path(root).resolve()
    results: list[VerificationResult] = []

    for relative in expected_files:
        target = (base / relative).resolve()
        safe = target == base or base in target.parents

        if not safe:
            results.append(
                VerificationResult(
                    check=f"file:{relative}",
                    passed=False,
                    detail=f"Expected file '{relative}' escapes the workspace root boundary.",
                )
            )
            continue

        if not target.exists():
            results.append(
                VerificationResult(
                    check=f"file:{relative}",
                    passed=False,
                    detail=f"Expected file '{relative}' is missing from the workspace.",
                )
            )
            continue

        results.append(
            VerificationResult(
                check=f"file:{relative}",
                passed=True,
                detail=f"Expected file '{relative}' exists inside workspace.",
            )
        )

        if target.is_file():
            syntax_check = verify_syntax(target)
            if syntax_check:
                results.append(syntax_check)

            test_check = verify_proof_of_test(target)
            if test_check:
                results.append(test_check)

            critic_check = verify_security_critic(target)
            if critic_check:
                results.append(critic_check)

    return results
