from pathlib import Path

from app.repository import inspect_repository
from app.repository_service import summarize_repository


def test_repository_inspection(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('ok')")
    (tmp_path / "README.md").write_text("# demo")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("ignored")
    result = inspect_repository(str(tmp_path))
    assert [item.path for item in result] == ["README.md", "app.py"]


def test_repository_summary(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("pass")
    summary = summarize_repository(str(tmp_path))
    assert summary["file_count"] == 1
    assert summary["languages"] == {"python": 1}
