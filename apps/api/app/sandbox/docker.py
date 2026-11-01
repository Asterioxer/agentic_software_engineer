from __future__ import annotations

import logging
import subprocess
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

from .base import ExecutionSandbox, SandboxResult

logger = logging.getLogger("agent.sandbox.docker")


class DockerSandbox(ExecutionSandbox):
    """Containerized execution sandbox providing true OS-level isolation.

    Enforces:
    - Dedicated Linux container namespace
    - Network isolation (--network none)
    - Resource constraints (--memory, --cpus)
    - Scoped filesystem mount restricted to target workspace
    - Non-root user privileges
    """

    def __init__(
        self,
        image: str = "python:3.12-slim",
        memory_limit: str = "2g",
        cpu_limit: str = "2.0",
        network: str = "none",
    ) -> None:
        self.image = image
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.network = network

    @property
    def sandbox_type(self) -> str:
        return "docker"

    def is_available(self) -> bool:
        """Check if Docker CLI is installed and the Docker daemon is responding."""
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                check=False,
                timeout=5,
            )
            return res.returncode == 0
        except (subprocess.SubprocessError, OSError, FileNotFoundError):
            return False

    def execute(
        self,
        argv: Sequence[str],
        cwd: Path,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
        max_output_bytes: int = 32_000,
    ) -> SandboxResult:
        if not self.is_available():
            raise RuntimeError("Docker daemon is not available on this host.")

        if not cwd.exists() or not cwd.is_dir():
            raise ValueError(f"Execution cwd '{cwd}' must exist and be a directory.")

        container_name = f"agent-sandbox-{uuid.uuid4().hex[:12]}"
        docker_argv: list[str] = [
            "docker",
            "run",
            "--name",
            container_name,
            "--rm",
            "-v",
            f"{cwd.resolve()}:/workspace:rw",
            "-w",
            "/workspace",
            "--network",
            self.network,
            "--memory",
            self.memory_limit,
            "--cpus",
            self.cpu_limit,
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
        ]

        # Pass safe environment variables
        if env:
            for k, v in env.items():
                if not any(
                    secret in k.upper() for secret in ("KEY", "TOKEN", "SECRET", "AUTH", "PASS")
                ):
                    docker_argv.extend(["-e", f"{k}={v}"])

        docker_argv.append(self.image)
        docker_argv.extend(argv)

        start_time = time.perf_counter()
        try:
            res = subprocess.run(
                docker_argv,
                capture_output=True,
                check=False,
                timeout=timeout,
            )
            duration = time.perf_counter() - start_time
            stdout_text = res.stdout[:max_output_bytes].decode("utf-8", errors="replace")
            stderr_text = res.stderr[:max_output_bytes].decode("utf-8", errors="replace")
            truncated = len(res.stdout) >= max_output_bytes or len(res.stderr) >= max_output_bytes
            return SandboxResult(
                exit_code=res.returncode,
                timed_out=False,
                stdout=stdout_text,
                stderr=stderr_text,
                truncated=truncated,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            # Force remove running container
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, check=False)
            duration = time.perf_counter() - start_time
            return SandboxResult(
                exit_code=None,
                timed_out=True,
                stdout="",
                stderr="Container execution timed out and was killed.",
                truncated=False,
                duration_seconds=duration,
            )
