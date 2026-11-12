from __future__ import annotations

from pathlib import Path

from app.codegraph import CodeGraph


def test_codegraph_relative_import_resolution_and_cycle_detection(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "service_a.py").write_text("from .service_b import ServiceB\n", encoding="utf-8")
    (pkg / "service_b.py").write_text("from .service_c import ServiceC\n", encoding="utf-8")
    (pkg / "service_c.py").write_text("from .service_a import ServiceA\n", encoding="utf-8")

    graph = CodeGraph(tmp_path).build()
    cycles = graph.detect_cycles()

    assert len(cycles) == 1
    cycle = cycles[0]
    assert cycle[0] == cycle[-1]  # Closed loop
    assert "pkg/service_a.py" in cycle
    assert "pkg/service_b.py" in cycle
    assert "pkg/service_c.py" in cycle


def test_codegraph_find_orphan_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "main.py").write_text("from .used import used_func\n", encoding="utf-8")
    (src / "used.py").write_text("def used_func(): pass\n", encoding="utf-8")
    (src / "abandoned.py").write_text("def dead(): pass\n", encoding="utf-8")

    graph = CodeGraph(tmp_path).build()
    orphans = graph.find_orphan_files(ignore_entrypoints=True)

    assert "src/abandoned.py" in orphans
    assert "src/main.py" not in orphans  # Entrypoint ignored
    assert "src/used.py" not in orphans  # Imported by main
