from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from app.command_runner import CommandRunner
from app.sandbox import (
    DockerSandbox,
    ExecutionSandbox,
    LocalSubprocessSandbox,
    SandboxResult,
    get_default_sandbox,
)


def test_local_sandbox_execution(tmp_path: Path) -> None:
    sandbox = LocalSubprocessSandbox()
    assert sandbox.sandbox_type == "local_subprocess"
    assert sandbox.is_available()

    result = sandbox.execute(
        argv=["python", "-c", "print('hello-sandbox')"],
        cwd=tmp_path,
        timeout=5.0,
    )
    assert result.exit_code == 0
    assert not result.timed_out
    assert "hello-sandbox" in result.stdout
    assert result.duration_seconds > 0.0


def test_local_sandbox_timeout(tmp_path: Path) -> None:
    sandbox = LocalSubprocessSandbox()
    result = sandbox.execute(
        argv=["python", "-c", "import time; time.sleep(5)"],
        cwd=tmp_path,
        timeout=0.3,
    )
    assert result.timed_out
    assert result.exit_code is None


def test_local_sandbox_env_sanitization(tmp_path: Path) -> None:
    sandbox = LocalSubprocessSandbox()
    test_code = (
        "import os\n"
        "print('SAFE:' + os.environ.get('SAFE_VAR', 'NONE'))\n"
        "print('LEAKED:' + os.environ.get('SECRET_TOKEN', 'NONE'))\n"
    )
    result = sandbox.execute(
        argv=["python", "-c", test_code],
        cwd=tmp_path,
        env={"SAFE_VAR": "visible_value", "SECRET_TOKEN": "super_secret_123"},
    )
    assert "SAFE:visible_value" in result.stdout
    assert "LEAKED:NONE" in result.stdout
    assert "super_secret_123" not in result.stdout


def test_local_sandbox_output_truncation(tmp_path: Path) -> None:
    sandbox = LocalSubprocessSandbox()
    result = sandbox.execute(
        argv=["python", "-c", "print('A' * 2000)"],
        cwd=tmp_path,
        max_output_bytes=500,
    )
    assert result.truncated
    assert len(result.stdout.encode("utf-8")) <= 500


def test_local_sandbox_invalid_cwd(tmp_path: Path) -> None:
    sandbox = LocalSubprocessSandbox()
    non_existent = tmp_path / "does_not_exist"
    with pytest.raises(ValueError, match="must exist"):
        sandbox.execute(argv=["python", "-c", "print(1)"], cwd=non_existent)


def test_docker_sandbox_availability_check() -> None:
    docker_box = DockerSandbox()
    assert docker_box.sandbox_type == "docker"
    # Calling is_available should not raise an unhandled exception
    available = docker_box.is_available()
    assert isinstance(available, bool)


def test_docker_sandbox_fallback_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docker_box = DockerSandbox()
    monkeypatch.setattr(docker_box, "is_available", lambda: False)

    with pytest.raises(RuntimeError, match="Docker daemon is not available"):
        docker_box.execute(argv=["python", "--version"], cwd=tmp_path)


def test_get_default_sandbox_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default is local
    sandbox = get_default_sandbox(prefer_container=False)
    assert isinstance(sandbox, LocalSubprocessSandbox)

    # When prefer_container=True but docker unavailable, falls back to local
    monkeypatch.setattr(DockerSandbox, "is_available", lambda self: False)
    fallback = get_default_sandbox(prefer_container=True)
    assert isinstance(fallback, LocalSubprocessSandbox)


def test_command_runner_with_injected_sandbox(tmp_path: Path) -> None:
    class MockSandbox(ExecutionSandbox):
        @property
        def sandbox_type(self) -> str:
            return "mock"

        def is_available(self) -> bool:
            return True

        def execute(
            self,
            argv: Sequence[str],
            cwd: Path,
            timeout: float = 30.0,
            env: dict[str, str] | None = None,
            max_output_bytes: int = 32_000,
        ) -> SandboxResult:
            return SandboxResult(
                exit_code=0,
                timed_out=False,
                stdout="mocked diff check ok",
                stderr="",
                truncated=False,
                duration_seconds=0.01,
            )

    runner = CommandRunner(str(tmp_path), sandbox=MockSandbox())
    res = runner.run("git.diff.check")
    assert res.exit_code == 0
    assert res.stdout == "mocked diff check ok"
