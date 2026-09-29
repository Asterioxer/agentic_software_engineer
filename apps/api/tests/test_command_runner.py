from pathlib import Path
import pytest
from app.command_runner import CommandPolicy, CommandRunner

def test_unknown_command_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CommandRunner(str(tmp_path)).run("shell")

def test_runner_uses_structured_argv(tmp_path: Path) -> None:
    result = CommandRunner(str(tmp_path)).run("git.diff.check")
    assert result.argv == ("git", "diff", "--check")

def test_compile_accepts_only_structured_extra_args(tmp_path: Path) -> None:
    result = CommandRunner(str(tmp_path)).run("python.compile", ("app",))
    assert result.argv == ("python", "-m", "compileall", "app")

def test_non_compile_commands_reject_extra_args(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CommandRunner(str(tmp_path)).run("git.diff.check", ("--exit-code",))

def test_timeout_is_capped() -> None:
    assert CommandPolicy.MAX_TIMEOUT == 60.0
