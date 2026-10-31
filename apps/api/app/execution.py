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
    """Bounded workspace executor.

    IMPORTANT SAFETY NOTICE:
    This provides application-level directory containment and action allowlisting.
    It is NOT an OS-level sandbox. Untrusted code should be run in a disposable container.
    """

    def __init__(self, root: str, dry_run: bool = True) -> None:
        self.root = Path(root).resolve()
        self.dry_run = dry_run

    def _safe_path(self, relative_path: str) -> Path:
        if "\0" in relative_path:
            raise ValueError("Path contains null bytes.")

        # Disallow Windows drive prefixes or root overrides in relative paths
        clean_rel = relative_path.replace("\\", "/").strip()
        if clean_rel.startswith(("/", "\\")):
            clean_rel = clean_rel.lstrip("/\\")

        target = (self.root / clean_rel).resolve()

        # Strict containment check (resolves symlinks and directory junctions)
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Workspace path escapes the configured repository root.") from exc

        # Disallow sensitive VCS/environment internals directly
        forbidden_parts = {".git", ".env"}
        rel_parts = target.relative_to(self.root).parts
        if any(part in forbidden_parts for part in rel_parts):
            raise ValueError(
                "Direct modification of VCS internals or environment files is forbidden."
            )

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
                if target.is_dir():
                    raise ValueError(
                        "Directory deletion is not supported; delete files individually."
                    )
                target.unlink()
            return ActionResult(action.kind, action.path, True, "File deleted or already absent.")

        raise ValueError(f"Unsupported workspace action: {action.kind}")

    def apply_batch(self, actions: list[WorkspaceAction]) -> list[ActionResult]:
        return [self.apply(action) for action in actions]
