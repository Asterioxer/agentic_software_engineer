from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .command_runner import CommandRunner
from .execution import WorkspaceAction, WorkspaceExecutor
from .verification_pipeline import run_verification

ToolHandler = Callable[[dict[str, Any]], dict[str, Any]]

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    handler: ToolHandler

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition

    def get(self, name: str) -> ToolDefinition:
        return self._tools[name]

def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ToolDefinition(
        "repository.inspect",
        "Bounded repository metadata",
        lambda args: {"repository": args.get("repository"), "inspected": True},
    ))
    registry.register(ToolDefinition(
        "workspace.plan",
        "Validate and execute one bounded workspace action",
        lambda args: WorkspaceExecutor(
            str(args.get("repository") or "."),
            dry_run=bool(args.get("dry_run", True)),
        ).apply(WorkspaceAction(
            kind=str(args.get("kind", "write")),
            path=str(args.get("path", "agent-plan.txt")),
            content=args.get("content"),
        )).__dict__,
    ))
    registry.register(ToolDefinition(
        "command.run",
        "Run one allowlisted structured command",
        lambda args: CommandRunner(str(args.get("repository") or ".")).run(
            str(args.get("command_id", "git.diff.check")),
            tuple(str(x) for x in args.get("extra_args", [])),
        ).__dict__,
    ))
    registry.register(ToolDefinition(
        "verification.run",
        "Run independent workspace and command verification",
        lambda args: {
            "passed": evidence.passed,
            "checks": [check.model_dump() for check in evidence.checks],
        }
        if (evidence := run_verification(
            str(args.get("repository") or "."),
            list(args.get("expected_files", [])),
        )) else {},
    ))
    return registry
