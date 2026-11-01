from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SandboxResult:
    """Deterministic result of command execution in an isolated sandbox."""

    exit_code: int | None
    timed_out: bool
    stdout: str
    stderr: str
    truncated: bool
    duration_seconds: float


class ExecutionSandbox(ABC):
    """Abstract interface for OS-level or process-level execution sandboxes."""

    @property
    @abstractmethod
    def sandbox_type(self) -> str:
        """Identifier for the sandbox provider (e.g. 'local_subprocess', 'docker', 'gvisor')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this sandbox environment is installed and functional on the host."""
        ...

    @abstractmethod
    def execute(
        self,
        argv: Sequence[str],
        cwd: Path,
        timeout: float = 30.0,
        env: dict[str, str] | None = None,
        max_output_bytes: int = 32_000,
    ) -> SandboxResult:
        """Execute a structured argument vector in the sandbox."""
        ...
