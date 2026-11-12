from __future__ import annotations

import ast
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .code_context import IGNORED_DIRS, MAX_FILE_BYTES

logger = logging.getLogger("agent.codegraph")


@dataclass
class SymbolNode:
    name: str
    kind: str  # "class" | "function" | "async_function" | "export"
    file_path: str
    line_number: int


@dataclass
class BlastRadius:
    target_file: str
    direct_dependents: list[str]
    transitive_dependents: list[str]
    affected_tests: list[str]
    impact_level: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    total_impacted_files: int


class CodeGraph:
    """Dependency and symbol reference graph for analyzing architectural impact and blast radius."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.definitions: dict[str, list[SymbolNode]] = defaultdict(list)
        self.imports: dict[str, set[str]] = defaultdict(set)
        self.file_dependencies: dict[str, set[str]] = defaultdict(set)
        self.file_dependents: dict[str, set[str]] = defaultdict(set)
        self.call_references: dict[str, set[str]] = defaultdict(set)
        self.files_indexed: list[str] = []
        self._built = False

    def build(self) -> CodeGraph:
        """Parse workspace source files and construct the dependency graph."""
        if not self.root.is_dir():
            return self

        for path in self.root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                continue

            rel_str = path.relative_to(self.root).as_posix()
            self.files_indexed.append(rel_str)

            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            if path.suffix.lower() == ".py":
                self._index_python_file(rel_str, content)
            else:
                self._index_js_ts_file(rel_str, content)

        self._resolve_file_edges()
        self._built = True
        return self

    def _index_python_file(self, rel_path: str, code: str) -> None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                self.definitions[node.name].append(
                    SymbolNode(
                        name=node.name, kind=kind, file_path=rel_path, line_number=node.lineno
                    )
                )
            elif isinstance(node, ast.ClassDef):
                self.definitions[node.name].append(
                    SymbolNode(
                        name=node.name, kind="class", file_path=rel_path, line_number=node.lineno
                    )
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    self.imports[rel_path].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    rel_dir = Path(rel_path).parent
                    for _ in range(node.level - 1):
                        rel_dir = rel_dir.parent
                    if node.module:
                        resolved_rel = (rel_dir / node.module.replace(".", "/")).as_posix()
                        self.imports[rel_path].add(resolved_rel)
                    else:
                        for alias in node.names:
                            self.imports[rel_path].add((rel_dir / alias.name).as_posix())
                else:
                    mod = node.module or ""
                    self.imports[rel_path].add(mod)
                for alias in node.names:
                    self.call_references[alias.name].add(rel_path)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self.call_references[node.id].add(rel_path)

    def _index_js_ts_file(self, rel_path: str, code: str) -> None:
        # Match imports: import ... from './...' or require('...')
        for m in re.finditer(r"""(?:from|require)\s*\(?['"]([^'"]+)['"]\)?;?""", code):
            self.imports[rel_path].add(m.group(1))

        # Match definitions: export function / class / const
        for m in re.finditer(
            r"""export\s+(?:default\s+)?(function|class|const|interface|type)\s+([A-Za-z0-9_$]+)""",
            code,
        ):
            self.definitions[m.group(2)].append(
                SymbolNode(name=m.group(2), kind=m.group(1), file_path=rel_path, line_number=1)
            )

    def _resolve_file_edges(self) -> None:
        """Resolve symbolic import strings into exact relative file path edges."""
        file_map: dict[str, str] = {}
        for f in self.files_indexed:
            # Map without suffix, e.g. "app/cli" -> "app/cli.py"
            stem = str(Path(f).with_suffix("")).replace("\\", "/")
            file_map[stem] = f
            # Also map module dot notation, e.g. "app.cli" -> "app/cli.py"
            file_map[stem.replace("/", ".")] = f
            # Also base stem
            file_map[Path(f).stem] = f
            # If __init__.py, also map package directory
            if Path(f).name == "__init__.py":
                pkg_dir = Path(f).parent.as_posix()
                file_map[pkg_dir] = f
                file_map[pkg_dir.replace("/", ".")] = f

        for src, raw_imports in self.imports.items():
            for imp in raw_imports:
                clean_imp = imp.lstrip("./").replace("\\", "/")
                matched = file_map.get(clean_imp) or file_map.get(imp)
                if matched and matched != src:
                    self.file_dependencies[src].add(matched)
                    self.file_dependents[matched].add(src)

    def get_blast_radius(self, target_file: str, max_depth: int = 5) -> BlastRadius:
        """Calculate direct, transitive dependents and affected tests for a given file."""
        if not self._built:
            self.build()

        norm_target = Path(target_file).as_posix().lstrip("./")
        # Direct dependents
        direct = sorted(self.file_dependents.get(norm_target, set()))

        # Transitive dependents BFS
        transitive: set[str] = set()
        queue: list[tuple[str, int]] = [(norm_target, 0)]
        visited: set[str] = {norm_target}

        while queue:
            curr, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            for dep in self.file_dependents.get(curr, set()):
                if dep not in visited:
                    visited.add(dep)
                    transitive.add(dep)
                    queue.append((dep, depth + 1))

        all_affected = sorted(transitive)
        affected_tests = [
            f for f in all_affected if "test" in Path(f).name.lower() or "tests/" in f.lower()
        ]

        total = len(all_affected)
        if total == 0:
            impact = "LOW"
        elif total <= 2:
            impact = "MEDIUM"
        elif total <= 8:
            impact = "HIGH"
        else:
            impact = "CRITICAL"

        return BlastRadius(
            target_file=norm_target,
            direct_dependents=direct,
            transitive_dependents=all_affected,
            affected_tests=affected_tests,
            impact_level=impact,
            total_impacted_files=total,
        )

    def find_symbol(self, name: str) -> list[dict[str, Any]]:
        if not self._built:
            self.build()
        nodes = self.definitions.get(name, [])
        return [
            {
                "name": n.name,
                "kind": n.kind,
                "file_path": n.file_path,
                "line_number": n.line_number,
            }
            for n in nodes
        ]

    def summary(self) -> dict[str, Any]:
        if not self._built:
            self.build()
        total_edges = sum(len(deps) for deps in self.file_dependencies.values())
        return {
            "root": str(self.root),
            "files_indexed": len(self.files_indexed),
            "definitions_count": sum(len(v) for v in self.definitions.values()),
            "unique_symbols": len(self.definitions),
            "dependency_edges": total_edges,
        }

    def detect_cycles(self) -> list[list[str]]:
        """Detect circular dependency cycles between indexed source files.

        Returns a sorted list of unique cycle loops, e.g. [['a.py', 'b.py', 'a.py']].
        """
        if not self._built:
            self.build()

        cycles: set[tuple[str, ...]] = set()

        def dfs(current: str, path: list[str], visited_in_path: set[str]) -> None:
            path.append(current)
            visited_in_path.add(current)

            for neighbor in sorted(self.file_dependencies.get(current, set())):
                if neighbor in visited_in_path:
                    cycle_start_idx = path.index(neighbor)
                    cycle_nodes = path[cycle_start_idx:]
                    if len(cycle_nodes) > 1:
                        min_idx = cycle_nodes.index(min(cycle_nodes))
                        canonical = cycle_nodes[min_idx:] + cycle_nodes[:min_idx]
                        cycles.add(tuple(canonical + [canonical[0]]))
                elif neighbor not in path:
                    dfs(neighbor, path, visited_in_path)

            visited_in_path.remove(current)
            path.pop()

        for node in sorted(self.files_indexed):
            dfs(node, [], set())

        return [list(c) for c in sorted(cycles)]

    def find_orphan_files(self, ignore_entrypoints: bool = True) -> list[str]:
        """Find source files that are never imported or depended upon by any other file."""
        if not self._built:
            self.build()

        orphans: list[str] = []
        entrypoint_names = {
            "main.py",
            "__main__.py",
            "__init__.py",
            "cli.py",
            "wsgi.py",
            "asgi.py",
            "index.ts",
            "index.tsx",
            "index.js",
            "index.jsx",
            "page.tsx",
            "layout.tsx",
            "route.ts",
        }

        for f in sorted(self.files_indexed):
            if len(self.file_dependents.get(f, set())) > 0:
                continue

            if ignore_entrypoints:
                fname = Path(f).name.lower()
                if fname in entrypoint_names:
                    continue
                if "test" in fname or "tests/" in f.lower() or "__tests__" in f.lower():
                    continue

            orphans.append(f)

        return orphans
