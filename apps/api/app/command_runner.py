from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from .sandbox import ExecutionSandbox, get_default_sandbox


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
    This does NOT provide OS-level process virtualization or container sandboxing on its own.
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
    """Runs allowlisted structured commands inside the repository root via a pluggable sandbox."""

    def __init__(
        self,
        root: str,
        policy: CommandPolicy | None = None,
        sandbox: ExecutionSandbox | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.policy = policy or CommandPolicy()
        self.sandbox = sandbox or get_default_sandbox()

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

        sb_result = self.sandbox.execute(
            argv=spec.argv,
            cwd=self.root,
            timeout=timeout,
            max_output_bytes=self.policy.MAX_OUTPUT_BYTES,
        )

        return CommandResult(
            id=command_id,
            argv=spec.argv,
            exit_code=sb_result.exit_code,
            timed_out=sb_result.timed_out,
            stdout=sb_result.stdout,
            stderr=sb_result.stderr,
            truncated=sb_result.truncated,
        )
