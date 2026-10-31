from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .code_context import retrieve_relevant_context
from .command_runner import CommandRunner
from .domain import EvidenceRecord
from .execution import WorkspaceAction, WorkspaceExecutor
from .repository_service import summarize_repository
from .verification_pipeline import run_verification

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]


class RepositoryInspectArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repository: str | None = None
    query: str = ""
    max_files: int = Field(default=500, ge=1, le=1000)


class WorkspacePlanArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repository: str | None = None
    dry_run: bool = True
    kind: str = Field(default="write")
    path: str = Field(default="agent-plan.txt")
    content: str | None = None


class CommandRunArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repository: str | None = None
    command_id: str = "git.diff.check"
    extra_args: list[str] = Field(default_factory=list)
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=60.0)


class VerificationRunArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")
    repository: str | None = None
    expected_files: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler
    input_schema: type[BaseModel] | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        if name not in self._tools:
            raise KeyError(f"Tool not registered: {name}")
        return self._tools[name]

    def execute_guarded(
        self, name: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any], EvidenceRecord]:
        """Validate input arguments schema, execute tool, and produce structured evidence record."""
        tool = self.get(name)
        start_time = time.monotonic()

        validated_args = args
        if tool.input_schema:
            validated_obj = tool.input_schema.model_validate(args)
            validated_args = validated_obj.model_dump()

        result = tool.handler(validated_args)
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)

        passed = not bool(result.get("error")) and result.get("exit_code", 0) in (0, None)
        record = EvidenceRecord(
            source=name,
            category="tool_execution",
            summary=f"Tool {name} executed in {duration_ms}ms (passed={passed})",
            passed=passed,
            data={"arguments": validated_args, "result": result, "duration_ms": duration_ms},
        )
        return result, record


def _handle_repository_inspect(args: dict[str, Any]) -> dict[str, Any]:
    repo = args.get("repository")
    if not repo:
        return {"repository": None, "inspected": False, "summary": None, "snippets": []}
    summary = summarize_repository(repo)
    query = str(args.get("query", ""))
    snippets = [s.__dict__ for s in retrieve_relevant_context(repo, query)]
    return {
        "repository": repo,
        "inspected": True,
        "summary": summary,
        "snippets": snippets,
    }


def _handle_workspace_plan(args: dict[str, Any]) -> dict[str, Any]:
    repo = str(args.get("repository") or ".")
    dry_run = bool(args.get("dry_run", True))
    kind = str(args.get("kind", "write"))
    path = str(args.get("path", "agent-plan.txt"))
    raw_content = args.get("content")
    content = raw_content if raw_content is not None else "# Bounded execution plan\n"

    executor = WorkspaceExecutor(repo, dry_run=dry_run)
    action_result = executor.apply(WorkspaceAction(kind=kind, path=path, content=content))
    return action_result.__dict__


def _handle_command_run(args: dict[str, Any]) -> dict[str, Any]:
    repo = str(args.get("repository") or ".")
    command_id = str(args.get("command_id", "git.diff.check"))
    extra = tuple(str(x) for x in args.get("extra_args", []))
    timeout = float(args.get("timeout_seconds", 30.0))
    runner = CommandRunner(repo)
    res = runner.run(command_id, extra, timeout_seconds=timeout)
    return res.__dict__


def _handle_verification_run(args: dict[str, Any]) -> dict[str, Any]:
    repo = str(args.get("repository") or ".")
    expected = list(args.get("expected_files", []))
    evidence = run_verification(repo, expected)
    return {
        "passed": evidence.passed,
        "checks": [c.model_dump() for c in evidence.checks],
    }


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            "repository.inspect",
            "Bounded repository metadata and code snippets retrieval",
            _handle_repository_inspect,
            RepositoryInspectArgs,
        )
    )
    registry.register(
        ToolDefinition(
            "workspace.plan",
            "Validate and execute one bounded workspace action (dry-run default)",
            _handle_workspace_plan,
            WorkspacePlanArgs,
        )
    )
    registry.register(
        ToolDefinition(
            "command.run",
            "Run one allowlisted structured command without arbitrary shell",
            _handle_command_run,
            CommandRunArgs,
        )
    )
    registry.register(
        ToolDefinition(
            "verification.run",
            "Run independent workspace and command verification",
            _handle_verification_run,
            VerificationRunArgs,
        )
    )
    return registry
