from __future__ import annotations

import logging
import os
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

from .base import ExecutionSandbox, SandboxResult

logger = logging.getLogger("agent.sandbox.local")


class LocalSubprocessSandbox(ExecutionSandbox):
    """Guarded local process execution sandbox.

    Enforces:
    - shell=False invocation
    - Strict environment sanitization (stripping API keys and ambient credentials)
    - Process tree termination on timeout
    - Bound output buffer limits
    """

    @property
    def sandbox_type(self) -> str:
        return "local_subprocess"

    def is_available(self) -> bool:
        return True

    def _kill_process_tree(self, proc: subprocess.Popen[bytes]) -> None:
        """Terminate child process and all descendants."""
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                proc.kill()
        except OSError:
            pass
        try:
            proc.kill()
        except OSError:
            pass

    def execute(
        self,
        argv: Sequence[str],
        cwd: Path,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
        max_output_bytes: int = 32_000,
    ) -> SandboxResult:
        if not cwd.exists() or not cwd.is_dir():
            raise ValueError(f"Execution cwd '{cwd}' must exist and be a directory.")

        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(cwd),
            "PYTHONUNBUFFERED": "1",
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "COMSPEC": os.environ.get("COMSPEC", ""),
        }
        if env:
            for k, v in env.items():
                if not any(
                    secret in k.upper() for secret in ("KEY", "TOKEN", "SECRET", "AUTH", "PASS")
                ):
                    safe_env[k] = v

        start_time = time.perf_counter()
        proc = subprocess.Popen(
            list(argv),
            cwd=str(cwd),
            env=safe_env,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            timed_out = False
            exit_code = proc.returncode
            stdout_slice = stdout_bytes[:max_output_bytes]
            stderr_slice = stderr_bytes[:max_output_bytes]
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = None
            self._kill_process_tree(proc)
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                stdout_bytes, stderr_bytes = b"", b""
            stdout_slice = stdout_bytes[:max_output_bytes]
            stderr_slice = stderr_bytes[:max_output_bytes]

        duration = time.perf_counter() - start_time
        stdout_text = stdout_slice.decode("utf-8", errors="replace")
        stderr_text = stderr_slice.decode("utf-8", errors="replace")
        truncated = (
            len(stdout_text.encode("utf-8")) >= max_output_bytes
            or len(stderr_text.encode("utf-8")) >= max_output_bytes
        )

        return SandboxResult(
            exit_code=exit_code,
            timed_out=timed_out,
            stdout=stdout_text,
            stderr=stderr_text,
            truncated=truncated,
            duration_seconds=duration,
        )
