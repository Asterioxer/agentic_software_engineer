from pathlib import Path

from app.patch import PatchApplier, parse_unified_diff
from app.tools import build_default_registry

SAMPLE_DIFF = """--- a/src/math_ops.py
+++ b/src/math_ops.py
@@ -1,3 +1,6 @@
 def add(a: int, b: int) -> int:
     return a + b
+
+def multiply(a: int, b: int) -> int:
+    return a * b
"""


def test_parse_unified_diff() -> None:
    patches = parse_unified_diff(SAMPLE_DIFF)
    assert len(patches) == 1
    patch = patches[0]
    assert patch.source_path == "src/math_ops.py"
    assert patch.target_path == "src/math_ops.py"
    assert len(patch.hunks) == 1
    hunk = patch.hunks[0]
    assert hunk.old_start == 1
    assert hunk.new_start == 1
    assert any("+def multiply" in line for line in hunk.lines)


def test_patch_applier_dry_run(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    target_file = src_dir / "math_ops.py"
    original_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    target_file.write_text(original_code, encoding="utf-8")

    applier = PatchApplier(str(tmp_path), dry_run=True)
    res = applier.apply_diff(SAMPLE_DIFF)

    assert not res.applied
    assert res.modified_files == ["src/math_ops.py"]
    assert res.error is None
    # Disk should remain unchanged in dry run
    assert target_file.read_text(encoding="utf-8") == original_code


def test_patch_applier_apply_success(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    target_file = src_dir / "math_ops.py"
    original_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    target_file.write_text(original_code, encoding="utf-8")

    applier = PatchApplier(str(tmp_path), dry_run=False)
    res = applier.apply_diff(SAMPLE_DIFF)

    assert res.applied
    assert res.modified_files == ["src/math_ops.py"]
    assert "src/math_ops.py" in res.file_hashes
    updated_code = target_file.read_text(encoding="utf-8")
    assert "def multiply" in updated_code


def test_patch_applier_mismatch_rollback(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    target_file = src_dir / "math_ops.py"
    # Content doesn't match hunk context
    mismatched_code = "def subtract(a: int, b: int) -> int:\n    return a - b\n"
    target_file.write_text(mismatched_code, encoding="utf-8")

    applier = PatchApplier(str(tmp_path), dry_run=False)
    res = applier.apply_diff(SAMPLE_DIFF)

    assert not res.applied
    assert "mismatch at line" in str(res.error)
    # File must be untouched
    assert target_file.read_text(encoding="utf-8") == mismatched_code


def test_patch_applier_path_traversal_rejection(tmp_path: Path) -> None:
    malicious_diff = """--- a/../../outside.txt
+++ b/../../outside.txt
@@ -1,1 +1,2 @@
 line1
+malicious line
"""
    applier = PatchApplier(str(tmp_path), dry_run=False)
    res = applier.apply_diff(malicious_diff)
    assert not res.applied
    assert "Path traversal attempted" in str(res.error)


def test_workspace_patch_tool_execution(tmp_path: Path) -> None:
    registry = build_default_registry()
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    target_file = src_dir / "math_ops.py"
    target_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    result, record = registry.execute_guarded(
        "workspace.patch",
        {
            "repository": str(tmp_path),
            "diff": SAMPLE_DIFF,
            "dry_run": False,
        },
    )
    assert result["applied"] is True
    assert record.passed is True
    assert "def multiply" in target_file.read_text(encoding="utf-8")
