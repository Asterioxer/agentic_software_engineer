from __future__ import annotations

from pathlib import Path

from .repository import inspect_repository


def summarize_repository(root: str) -> dict[str, object]:
    files = inspect_repository(root)
    languages: dict[str, int] = {}
    for item in files:
        languages[item.language] = languages.get(item.language, 0) + 1
    return {
        "root": str(Path(root).resolve()),
        "file_count": len(files),
        "languages": languages,
        "files": [item.__dict__ for item in files],
    }
