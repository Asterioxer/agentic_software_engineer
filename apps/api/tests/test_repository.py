from pathlib import Path

from app.repository import inspect_repository
from app.repository_service import (
    detect_frameworks,
    map_source_to_tests,
    parse_dependency_manifests,
    summarize_repository,
)


def test_repository_inspection(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "README.md").write_text("# demo", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")
    result = inspect_repository(str(tmp_path))
    assert [item.path for item in result] == ["README.md", "app.py"]


def test_repository_summary(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("pass", encoding="utf-8")
    summary = summarize_repository(str(tmp_path))
    assert summary["file_count"] == 1
    assert summary["languages"] == {"python": 1}
    assert "manifests" in summary
    assert "frameworks" in summary
    assert "test_mappings" in summary


def test_parse_manifests_and_detect_frameworks(tmp_path: Path) -> None:
    # Pyproject
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my-service"\nversion = "1.0.0"\ndependencies = ["fastapi>=0.115", "pytest>=8.0"]\n',
        encoding="utf-8",
    )
    # Package json
    (tmp_path / "package.json").write_text(
        '{"name": "web-ui", "dependencies": {"next": "15.0.0", "react": "19.0.0"}}',
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text("def test_add(): pass\n", encoding="utf-8")

    manifests = parse_dependency_manifests(tmp_path)
    assert "pyproject.toml" in manifests
    assert "package.json" in manifests
    assert manifests["pyproject.toml"]["name"] == "my-service"

    files = inspect_repository(str(tmp_path))
    frameworks = detect_frameworks(manifests, files)
    assert "FastAPI" in frameworks
    assert "Pytest" in frameworks
    assert "Next.js" in frameworks
    assert "React" in frameworks

    mappings = map_source_to_tests(files)
    assert any("calc.py" in src for src in mappings)
    assert any("test_calc.py" in t for src, targets in mappings.items() for t in targets)
