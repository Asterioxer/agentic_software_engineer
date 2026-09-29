from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

@dataclass(frozen=True)
class FileChange:
    path: str
    additions: int
    deletions: int
    risk: str

@dataclass(frozen=True)
class ChangeAnalysis:
    files: list[FileChange]
    total_additions: int
    total_deletions: int
    risk: str

def analyze_diff(diff: str) -> ChangeAnalysis:
    files: list[FileChange] = []
    current: str | None = None
    additions = deletions = 0

    def flush() -> None:
        nonlocal additions, deletions
        if current is not None:
            files.append(FileChange(current, additions, deletions, _file_risk(current, additions, deletions)))
        additions = deletions = 0

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            flush()
            current = line[6:]
        elif current and line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif current and line.startswith("-") and not line.startswith("---"):
            deletions += 1
    flush()

    total_additions = sum(item.additions for item in files)
    total_deletions = sum(item.deletions for item in files)
    risk = "high" if any(item.risk == "high" for item in files) else "medium" if any(item.risk == "medium" for item in files) else "low"
    return ChangeAnalysis(files, total_additions, total_deletions, risk)

def _file_risk(path: str, additions: int, deletions: int) -> str:
    p = PurePosixPath(path)
    sensitive = {"auth", "security", "migration", "infra", "deploy", ".github"}
    if any(part in sensitive or any(token in part.lower() for token in sensitive) for part in p.parts):
        return "high"
    if p.suffix in {".sql", ".tf", ".yml", ".yaml"} or additions + deletions > 200:
        return "medium"
    return "low"
