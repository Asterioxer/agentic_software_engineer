from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar


@dataclass(frozen=True)
class CommandSpec:
    id: str
    argv: tuple[str, ...]
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class CommandResult:
    id: str
    argv: tuple[str, ...]
    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    truncated: bool


class CommandPolicy:
    """Allowlist of structured commands.

    SAFETY WARNING:
    Application-level command filter using shell=False.
    This does NOT provide OS-level process virtualization or container sandboxing.
    """

    ALLOWED: ClassVar[dict[str, tuple[str, ...]]] = {
        "python.tests": ("python", "-m", "pytest"),
        "python.compile": ("python", "-m", "compileall"),
        "git.diff.check": ("git", "diff", "--check"),
        "git.status": ("git", "status", "--short"),
        "git.diff": ("git", "diff"),
        "python.ruff": ("python", "-m", "ruff", "check"),
    }
    MAX_TIMEOUT = 60.0
    MAX_OUTPUT_BYTES = 32_000

    def resolve(self, command_id: str, extra_args: tuple[str, ...] = ()) -> CommandSpec:
        if command_id not in self.ALLOWED:
            raise ValueError(f"Command '{command_id}' is not allowlisted.")
        base = self.ALLOWED[command_id]
        if command_id == "python.compile" and extra_args:
            return CommandSpec(command_id, base + extra_args)
        if extra_args:
            raise ValueError(f"Command '{command_id}' does not accept arguments.")
        return CommandSpec(command_id, base)


class CommandRunner:
    """Runs allowlisted structured commands inside the repository root with process tree cleanup."""

    def __init__(self, root: str, policy: CommandPolicy | None = None) -> None:
        self.root = Path(root).resolve()
        self.policy = policy or CommandPolicy()

    def _kill_process_tree(self, proc: subprocess.Popen[bytes]) -> None:
        """Safely terminate child process and all descendants on timeout."""
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

    def run(
        self,
        command_id: str,
        extra_args: tuple[str, ...] = (),
        timeout_seconds: float = 30.0,
    ) -> CommandResult:
        if not self.root.exists() or not self.root.is_dir():
            raise ValueError("Command workspace root must be an existing directory.")
        timeout = min(timeout_seconds, self.policy.MAX_TIMEOUT)
        if timeout <= 0:
            raise ValueError("Command timeout must be positive.")
        spec = self.policy.resolve(command_id, extra_args)

        # Filtered environment: disallow passing ambient credentials, tokens, or arbitrary env
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(self.root),
            "PYTHONUNBUFFERED": "1",
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
            "COMSPEC": os.environ.get("COMSPEC", ""),
        }

        proc = subprocess.Popen(
            list(spec.argv),
            cwd=self.root,
            env=safe_env,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            timed_out = False
            exit_code = proc.returncode
            stdout = stdout_bytes[: self.policy.MAX_OUTPUT_BYTES]
            stderr = stderr_bytes[: self.policy.MAX_OUTPUT_BYTES]
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = None
            self._kill_process_tree(proc)
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                stdout_bytes, stderr_bytes = b"", b""
            stdout = stdout_bytes[: self.policy.MAX_OUTPUT_BYTES]
            stderr = stderr_bytes[: self.policy.MAX_OUTPUT_BYTES]

        stdout_text = (
            stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else str(stdout)
        )
        stderr_text = (
            stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else str(stderr)
        )
        truncated = (
            len(stdout_text.encode()) >= self.policy.MAX_OUTPUT_BYTES
            or len(stderr_text.encode()) >= self.policy.MAX_OUTPUT_BYTES
        )
        return CommandResult(
            command_id, spec.argv, exit_code, timed_out, stdout_text, stderr_text, truncated
        )
