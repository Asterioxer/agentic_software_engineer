from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]


@dataclass(frozen=True)
class CriticFinding:
    rule_id: str
    severity: Severity
    file_path: str
    line_number: int | None
    description: str
    recommendation: str


@dataclass(frozen=True)
class CriticReview:
    approved: bool
    risk_score: float  # 0.0 (safe) to 1.0 (critical risk)
    findings: list[CriticFinding]
    summary: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


# Security Regex Rules
SECRET_PATTERNS = [
    (
        r"(?i)(api[_-]?key|secret|token|password|auth_token)\s*=\s*['\"][A-Za-z0-9_\-\.]{8,}['\"]",
        "SEC-001",
        "CRITICAL",
        "Hardcoded API key or credential secret detected.",
    ),
    (r"AKIA[0-9A-Z]{16}", "SEC-001", "CRITICAL", "AWS Access Key ID detected."),
    (
        r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
        "SEC-001",
        "CRITICAL",
        "Embedded private cryptographic key detected.",
    ),
]

INSECURE_EXEC_PATTERNS = [
    (r"\beval\s*\(", "SEC-002", "HIGH", "Dynamic execution with eval() detected."),
    (r"\bexec\s*\(", "SEC-002", "HIGH", "Dynamic execution with exec() detected."),
    (
        r"os\.system\s*\(",
        "SEC-002",
        "HIGH",
        "Arbitrary shell invocation with os.system() detected.",
    ),
    (r"shell\s*=\s*True", "SEC-002", "CRITICAL", "Subprocess execution with shell=True detected."),
]

SQL_INJECTION_PATTERNS = [
    (
        r"(?i)f['\"]SELECT\s+.*\s+FROM\s+.*\{.+\}",
        "SEC-003",
        "CRITICAL",
        "Formatted string SQL query allows SQL injection.",
    ),
    (
        r"(?i)['\"]SELECT\s+.*\s+FROM\s+.*['\"]\s*%\s*",
        "SEC-003",
        "HIGH",
        "Percent-formatted SQL query allows SQL injection.",
    ),
]

PATH_TRAVERSAL_PATTERNS = [
    (
        r"(?i)open\s*\(\s*(request\.|params\.|args\.|user_input)",
        "SEC-004",
        "HIGH",
        "Direct unvalidated user input passed to open().",
    ),
]


def review_code_snippet(code: str, file_path: str = "snippet.py") -> list[CriticFinding]:
    """Scan a code string using AST analysis and heuristic pattern matching."""
    findings: list[CriticFinding] = []
    lines = code.splitlines()

    # Phase 1: Pattern Matching
    for line_idx, line in enumerate(lines, start=1):
        for pattern, rule_id, severity, desc in SECRET_PATTERNS:
            if re.search(pattern, line):
                findings.append(
                    CriticFinding(
                        rule_id=rule_id,
                        severity=severity,  # type: ignore[arg-type]
                        file_path=file_path,
                        line_number=line_idx,
                        description=desc,
                        recommendation="Store credentials in environment variables or a secrets manager.",
                    )
                )

        for pattern, rule_id, severity, desc in INSECURE_EXEC_PATTERNS:
            if re.search(pattern, line):
                findings.append(
                    CriticFinding(
                        rule_id=rule_id,
                        severity=severity,  # type: ignore[arg-type]
                        file_path=file_path,
                        line_number=line_idx,
                        description=desc,
                        recommendation="Avoid arbitrary code evaluation; use bounded deterministic parsers.",
                    )
                )

        for pattern, rule_id, severity, desc in SQL_INJECTION_PATTERNS:
            if re.search(pattern, line):
                findings.append(
                    CriticFinding(
                        rule_id=rule_id,
                        severity=severity,  # type: ignore[arg-type]
                        file_path=file_path,
                        line_number=line_idx,
                        description=desc,
                        recommendation="Use parameterized queries or an ORM with parameter bindings.",
                    )
                )

        for pattern, rule_id, severity, desc in PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, line):
                findings.append(
                    CriticFinding(
                        rule_id=rule_id,
                        severity=severity,  # type: ignore[arg-type]
                        file_path=file_path,
                        line_number=line_idx,
                        description=desc,
                        recommendation="Sanitize and resolve paths within an explicit root boundary before opening.",
                    )
                )

    # Phase 2: AST Analysis for Python files
    if file_path.endswith(".py"):
        try:
            tree = ast.parse(code, filename=file_path)
            for node in ast.walk(tree):
                # Detect subprocess calls with shell=True in AST
                if isinstance(node, ast.Call):
                    func_name = ""
                    if isinstance(node.func, ast.Attribute):
                        func_name = node.func.attr
                    elif isinstance(node.func, ast.Name):
                        func_name = node.func.id

                    if func_name in ("run", "Popen", "call", "check_call", "check_output"):
                        for kw in node.keywords:
                            if (
                                kw.arg == "shell"
                                and isinstance(kw.value, ast.Constant)
                                and kw.value.value is True
                            ):
                                findings.append(
                                    CriticFinding(
                                        rule_id="SEC-002",
                                        severity="CRITICAL",
                                        file_path=file_path,
                                        line_number=node.lineno,
                                        description="Subprocess called with shell=True via AST.",
                                        recommendation="Set shell=False and pass arguments as an explicit sequence.",
                                    )
                                )
        except SyntaxError:
            pass

    return findings


def review_diff(diff_text: str) -> CriticReview:
    """Analyze all additions in a unified diff and produce an overall critic review."""
    from .patch import parse_unified_diff

    patches = parse_unified_diff(diff_text)
    all_findings: list[CriticFinding] = []

    for patch in patches:
        added_lines: list[str] = []
        for hunk in patch.hunks:
            for line in hunk.lines:
                if line.startswith("+") and not line.startswith("+++"):
                    added_lines.append(line[1:])

        code_snippet = "\n".join(added_lines)
        file_findings = review_code_snippet(code_snippet, file_path=patch.target_path)
        all_findings.extend(file_findings)

    # Compute risk score
    severity_weights = {"CRITICAL": 0.5, "HIGH": 0.3, "MEDIUM": 0.15, "LOW": 0.05}
    risk_score = min(1.0, sum(severity_weights.get(f.severity, 0.1) for f in all_findings))

    # Reject if any CRITICAL or HIGH findings exist, or overall risk exceeds threshold
    approved = (
        not any(f.severity in ("CRITICAL", "HIGH") for f in all_findings) and risk_score < 0.5
    )

    if approved:
        summary = (
            f"Review approved with {len(all_findings)} minor finding(s)."
            if all_findings
            else "Review approved cleanly. No security violations detected."
        )
    else:
        critical_count = sum(1 for f in all_findings if f.severity in ("CRITICAL", "HIGH"))
        summary = f"Review rejected: {critical_count} critical/high security finding(s) detected."

    return CriticReview(
        approved=approved,
        risk_score=round(risk_score, 3),
        findings=all_findings,
        summary=summary,
    )


def review_workspace(root: str, files: list[str]) -> CriticReview:
    """Scan specific workspace files for security violations."""
    base = Path(root).resolve()
    all_findings: list[CriticFinding] = []

    for rel_path in files:
        target = (base / rel_path).resolve()
        if not target.is_file():
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            findings = review_code_snippet(content, file_path=rel_path)
            all_findings.extend(findings)
        except OSError:
            continue

    severity_weights = {"CRITICAL": 0.5, "HIGH": 0.3, "MEDIUM": 0.15, "LOW": 0.05}
    risk_score = min(1.0, sum(severity_weights.get(f.severity, 0.1) for f in all_findings))
    approved = (
        not any(f.severity in ("CRITICAL", "HIGH") for f in all_findings) and risk_score < 0.5
    )

    if approved:
        summary = (
            f"Workspace review approved with {len(all_findings)} minor finding(s)."
            if all_findings
            else "Clean workspace security review."
        )
    else:
        critical_count = sum(1 for f in all_findings if f.severity in ("CRITICAL", "HIGH"))
        summary = f"Workspace review rejected: {critical_count} critical/high finding(s) detected."

    return CriticReview(
        approved=approved,
        risk_score=round(risk_score, 3),
        findings=all_findings,
        summary=summary,
    )
