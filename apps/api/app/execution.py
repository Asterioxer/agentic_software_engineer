from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceAction:
    kind: str
    path: str
    content: str | None = None


@dataclass(frozen=True)
class ActionResult:
    kind: str
    path: str
    applied: bool
    detail: str


class WorkspaceExecutor:
    """Bounded executor. Dry-run is the default and paths cannot escape the workspace."""

    def __init__(self, root: str, dry_run: bool = True) -> None:
        self.root = Path(root).resolve()
        self.dry_run = dry_run

    def _safe_path(self, relative_path: str) -> Path:
        target = (self.root / relative_path).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("Workspace path escapes the configured repository root.")
        return target

    def apply(self, action: WorkspaceAction) -> ActionResult:
        target = self._safe_path(action.path)
        if action.kind == "write":
            if action.content is None:
                raise ValueError("Write actions require content.")
            if self.dry_run:
                return ActionResult(action.kind, action.path, False, "Dry-run: write not applied.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(action.content, encoding="utf-8")
            return ActionResult(action.kind, action.path, True, "File written.")
        if action.kind == "delete":
            if self.dry_run:
                return ActionResult(action.kind, action.path, False, "Dry-run: delete not applied.")
            if target.exists():
                target.unlink()
            return ActionResult(action.kind, action.path, True, "File deleted or already absent.")
        raise ValueError(f"Unsupported workspace action: {action.kind}")
