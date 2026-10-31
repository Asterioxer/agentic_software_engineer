from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

IGNORED_DIRS = frozenset(
    {
        ".git",
        ".next",
        "node_modules",
        "__pycache__",
        ".venv",
        "dist",
        "build",
        ".pytest_cache",
        ".ruff_cache",
        "agentic_engineer.db",
    }
)

MAX_FILE_BYTES = 100_000  # Skip reading excessively large files (>100KB) into context


@dataclass(frozen=True)
class CodeSnippet:
    path: str
    language: str
    content: str
    relevance_score: float
    symbols: list[str]


def sanitize_code_context(text: str) -> str:
    """Neutralize potential prompt-injection patterns in untrusted code."""
    # Defang system / instruction injection markers
    patterns = [
        (r"(?i)system\s*prompt\s*:", "[DEFANGED_PROMPT_HEADER]:"),
        (r"(?i)ignore\s+(all\s+)?previous\s+instructions", "[DEFANGED_INSTRUCTION_OVERRIDE]"),
        (r"(?i)you\s+are\s+now\s+in\s+developer\s+mode", "[DEFANGED_MODE_SWITCH]"),
        (r"<\s*/?\s*system\s*>", "[DEFANGED_TAG]"),
        (r"```\s*(system|admin|override)", "```code"),
    ]
    sanitized = text
    for pattern, replacement in patterns:
        sanitized = re.sub(pattern, replacement, sanitized)
    return sanitized


def extract_python_symbols(code: str) -> list[str]:
    """Extract top-level classes and functions using AST."""
    symbols: list[str] = []
    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(f"def {node.name}")
            elif isinstance(node, ast.ClassDef):
                symbols.append(f"class {node.name}")
    except SyntaxError:
        pass
    return symbols


def extract_js_ts_symbols(code: str) -> list[str]:
    """Extract exported classes, functions, and interfaces via regex."""
    symbols: list[str] = []
    for match in re.finditer(
        r"(?:export\s+)?(?:default\s+)?(function|class|interface|type|const)\s+([A-Za-z0-9_$]+)",
        code,
    ):
        symbols.append(f"{match.group(1)} {match.group(2)}")
    return symbols[:20]


def extract_symbols(path: str, code: str) -> list[str]:
    ext = Path(path).suffix.lower()
    if ext == ".py":
        return extract_python_symbols(code)
    if ext in {".ts", ".tsx", ".js", ".jsx"}:
        return extract_js_ts_symbols(code)
    return []


def retrieve_relevant_context(
    root: str,
    query: str,
    max_snippets: int = 5,
    max_chars_per_snippet: int = 2000,
) -> list[CodeSnippet]:
    """Retrieve code snippets ranked by keyword overlap with the task query."""
    base = Path(root).resolve()
    if not base.is_dir():
        return []

    query_tokens = set(re.findall(r"[A-Za-z0-9_]+", query.lower()))
    if not query_tokens:
        query_tokens = {"main", "app", "test", "run"}

    snippets: list[CodeSnippet] = []

    for file_path in base.rglob("*"):
        if not file_path.is_file():
            continue
        if any(part in IGNORED_DIRS for part in file_path.parts):
            continue
        if file_path.stat().st_size > MAX_FILE_BYTES:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_path = str(file_path.relative_to(base)).replace("\\", "/")
        path_lower = rel_path.lower()
        content_lower = content.lower()

        # Score based on token matches in path and content
        score = 0.0
        for token in query_tokens:
            if len(token) < 2:
                continue
            if token in path_lower:
                score += 5.0  # Path match carries higher weight
            matches = content_lower.count(token)
            if matches > 0:
                score += min(matches * 0.5, 5.0)

        if score > 0:
            symbols = extract_symbols(rel_path, content)
            truncated_content = sanitize_code_context(content[:max_chars_per_snippet])
            snippets.append(
                CodeSnippet(
                    path=rel_path,
                    language=file_path.suffix.lstrip("."),
                    content=truncated_content,
                    relevance_score=score,
                    symbols=symbols,
                )
            )

    snippets.sort(key=lambda item: item.relevance_score, reverse=True)
    return snippets[:max_snippets]
