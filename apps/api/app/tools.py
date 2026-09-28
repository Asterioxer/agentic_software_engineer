from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
        try:
            return self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            "repository.inspect",
            "Return bounded repository inspection metadata.",
            lambda args: {
                "repository": args.get("repository"),
                "inspected": True,
                "mode": "metadata-only",
            },
        )
    )
    registry.register(
        ToolDefinition(
            "workspace.plan",
            "Represent workspace actions without mutating files.",
            lambda args: {"actions": args.get("actions", []), "mutated": False},
        )
    )
    registry.register(
        ToolDefinition(
            "verification.run",
            "Evaluate deterministic verification inputs.",
            lambda args: {
                "checks": args.get("checks", []),
                "all_passed": all(bool(item.get("passed", False)) for item in args.get("checks", [])),
            },
        )
    )
    return registry
