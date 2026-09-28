from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

IGNORED = frozenset({".git", ".next", "node_modules", "__pycache__", ".venv", "dist", "build"})


@dataclass(frozen=True)
class RepositoryFile:
    path: str
    size: int
    language: str


def _language(path: Path) -> str:
    return {".py":"python",".ts":"typescript",".tsx":"typescript",".js":"javascript",".jsx":"javascript",".go":"go",".rs":"rust",".java":"java",".md":"markdown",".json":"json",".yml":"yaml",".yaml":"yaml"}.get(path.suffix.lower(),"other")


def inspect_repository(root: str, max_files: int = 500) -> list[RepositoryFile]:
    base = Path(root).resolve()
    if not base.is_dir():
        raise ValueError("Repository root does not exist or is not a directory.")
    files: list[RepositoryFile] = []
    for path in base.rglob("*"):
        if not path.is_file() or any(part in IGNORED for part in path.parts):
            continue
        files.append(RepositoryFile(str(path.relative_to(base)), path.stat().st_size, _language(path)))
        if len(files) >= max_files:
            break
    return sorted(files, key=lambda item: item.path)
