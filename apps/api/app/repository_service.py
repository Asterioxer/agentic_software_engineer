from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

from .repository import RepositoryFile, inspect_repository


def parse_dependency_manifests(root: Path) -> dict[str, Any]:
    """Parse common language dependency manifests."""
    manifests: dict[str, Any] = {}

    # 1. pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            project = data.get("project", {})
            deps = list(project.get("dependencies", []))
            manifests["pyproject.toml"] = {
                "name": project.get("name"),
                "version": project.get("version"),
                "dependencies": deps[:50],
            }
        except (tomllib.TOMLDecodeError, OSError):
            pass

    # 2. requirements.txt
    reqs = root / "requirements.txt"
    if reqs.is_file():
        try:
            lines = [
                line.strip().split(";")[0].split("==")[0].split(">=")[0].strip()
                for line in reqs.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            manifests["requirements.txt"] = {"dependencies": lines[:50]}
        except OSError:
            pass

    # 3. package.json
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = list(data.get("dependencies", {}).keys())
            dev_deps = list(data.get("devDependencies", {}).keys())
            manifests["package.json"] = {
                "name": data.get("name"),
                "version": data.get("version"),
                "dependencies": deps[:50],
                "devDependencies": dev_deps[:50],
                "scripts": list(data.get("scripts", {}).keys()),
            }
        except (json.JSONDecodeError, OSError):
            pass

    return manifests


def detect_frameworks(manifests: dict[str, Any], files: list[RepositoryFile]) -> list[str]:
    """Detect development frameworks and test runners in repository."""
    frameworks: set[str] = set()
    all_deps: set[str] = set()

    for m in manifests.values():
        if isinstance(m, dict):
            for d in m.get("dependencies", []):
                all_deps.add(str(d).lower().split("[")[0].strip())
            for d in m.get("devDependencies", []):
                all_deps.add(str(d).lower().split("[")[0].strip())

    file_paths = {f.path.lower() for f in files}

    # Python
    if any("fastapi" in d for d in all_deps):
        frameworks.add("FastAPI")
    if any("flask" in d for d in all_deps):
        frameworks.add("Flask")
    if any("django" in d for d in all_deps):
        frameworks.add("Django")
    if any("pytest" in d for d in all_deps) or any("test_" in p for p in file_paths):
        frameworks.add("Pytest")

    # JavaScript / TypeScript
    if any("next" in d for d in all_deps) or any(p.startswith("next.config.") for p in file_paths):
        frameworks.add("Next.js")
    if any("react" in d for d in all_deps):
        frameworks.add("React")
    if any("express" in d for d in all_deps):
        frameworks.add("Express")
    if any("jest" in d for d in all_deps):
        frameworks.add("Jest")

    return sorted(frameworks)


def map_source_to_tests(files: list[RepositoryFile]) -> dict[str, list[str]]:
    """Map source code files to their candidate test files."""
    test_files = [f.path for f in files if "test" in f.path.lower()]
    source_files = [
        f.path
        for f in files
        if f.language in {"python", "typescript", "javascript"} and "test" not in f.path.lower()
    ]
    mapping: dict[str, list[str]] = {}

    for src in source_files:
        stem = Path(src).stem.lower()
        candidates: list[str] = []
        for t in test_files:
            t_stem = Path(t).stem.lower()
            if stem in t_stem or t_stem.replace("test_", "").replace("_test", "") == stem:
                candidates.append(t)
        if candidates:
            mapping[src] = sorted(candidates)

    return mapping


def summarize_repository(root: str) -> dict[str, Any]:
    """Produce comprehensive repository intelligence summary."""
    base = Path(root).resolve()
    files = inspect_repository(root)
    languages: dict[str, int] = {}
    for item in files:
        languages[item.language] = languages.get(item.language, 0) + 1

    manifests = parse_dependency_manifests(base)
    frameworks = detect_frameworks(manifests, files)
    test_mappings = map_source_to_tests(files)

    return {
        "root": str(base),
        "file_count": len(files),
        "languages": languages,
        "files": [item.__dict__ for item in files],
        "manifests": manifests,
        "frameworks": frameworks,
        "test_mappings": test_mappings,
    }
