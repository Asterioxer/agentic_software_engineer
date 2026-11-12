from __future__ import annotations

from pathlib import Path

import pytest

from app.patch import PatchApplier


def test_patch_applier_rejects_git_hook_injection(tmp_path: Path) -> None:
    applier = PatchApplier(tmp_path)
    git_dir = tmp_path / ".git" / "hooks"
    git_dir.mkdir(parents=True)
    hook = git_dir / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    diff = """--- a/.git/hooks/pre-commit
+++ b/.git/hooks/pre-commit
@@ -1,2 +1,3 @@
 #!/bin/sh
+echo malicious
 exit 0
"""
    result = applier.apply_diff(diff)
    assert not result.applied
    assert result.error is not None
    assert "forbidden vcs internals" in result.error.lower()


def test_patch_applier_rejects_env_file_overwrite(tmp_path: Path) -> None:
    applier = PatchApplier(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET_KEY=original\n", encoding="utf-8")

    diff = """--- a/.env
+++ b/.env
@@ -1 +1 @@
-SECRET_KEY=original
+SECRET_KEY=hacked
"""
    result = applier.apply_diff(diff)
    assert not result.applied
    assert result.error is not None
    assert "environment files" in result.error.lower()


def test_patch_applier_rejects_null_byte_path_injection(tmp_path: Path) -> None:
    applier = PatchApplier(tmp_path)
    diff = """--- a/clean.txt\x00/../../etc/passwd
+++ b/clean.txt\x00/../../etc/passwd
@@ -0,0 +1 @@
+root::0:0:root:/:/bin/sh
"""
    result = applier.apply_diff(diff)
    assert not result.applied
    assert result.error is not None
    assert "null bytes" in result.error.lower()


def test_patch_applier_rejects_unc_and_ntfs_stream_paths(tmp_path: Path) -> None:
    applier = PatchApplier(tmp_path)
    unc_diff = """--- a///server/share/file.txt
+++ b///server/share/file.txt
@@ -0,0 +1 @@
+leak
"""
    result = applier.apply_diff(unc_diff)
    assert not result.applied
    assert result.error is not None
    assert "unc paths" in result.error.lower()

    ads_diff = """--- a/file.txt:evil_stream
+++ b/file.txt:evil_stream
@@ -0,0 +1 @@
+hidden
"""
    result_ads = applier.apply_diff(ads_diff)
    assert not result_ads.applied
    assert result_ads.error is not None
    assert "alternate data streams" in result_ads.error.lower()


def test_patch_applier_rejects_symlink_overwrite(tmp_path: Path) -> None:
    applier = PatchApplier(tmp_path)
    target = tmp_path.parent / "escape_victim.txt"
    target.write_text("secret_val\n", encoding="utf-8")

    symlink_file = tmp_path / "link_target.py"
    try:
        symlink_file.symlink_to(target)
    except OSError:
        pytest.skip("Symlink creation not permitted in this OS environment")

    diff = """--- a/link_target.py
+++ b/link_target.py
@@ -1 +1 @@
-secret_val
+hijacked_val
"""
    result = applier.apply_diff(diff)
    assert not result.applied
    assert result.error is not None
    assert "symlink" in result.error.lower()
