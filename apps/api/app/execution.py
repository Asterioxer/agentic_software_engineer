from __future__ import annotations

import hashlib
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
    precondition_hash: str | None = None
    postcondition_hash: str | None = None


def compute_file_hash(target: Path) -> str:
    """Compute deterministic SHA-256 hash of file content, or 'ABSENT' if not present."""
    if not target.exists() or not target.is_file():
        return "ABSENT"
    hasher = hashlib.sha256()
    with open(target, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class WorkspaceExecutor:
    """Bounded workspace executor with deterministic precondition/postcondition tracking.

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

    def compute_conditions(self, action: WorkspaceAction) -> tuple[str, str]:
        """Compute expected pre-condition and post-condition content hashes."""
        target = self._safe_path(action.path)
        pre_hash = compute_file_hash(target)
        if action.kind == "write":
            if action.content is None:
                raise ValueError("Write actions require content.")
            post_hash = hashlib.sha256(action.content.encode("utf-8")).hexdigest()
        elif action.kind == "delete":
            post_hash = "ABSENT"
        else:
            raise ValueError(f"Unsupported workspace action: {action.kind}")
        return pre_hash, post_hash

    def apply(self, action: WorkspaceAction) -> ActionResult:
        target = self._safe_path(action.path)
        pre_hash, expected_post_hash = self.compute_conditions(action)

        if action.kind == "write":
            if action.content is None:
                raise ValueError("Write actions require content.")
            if self.dry_run:
                return ActionResult(
                    action.kind,
                    action.path,
                    False,
                    "Dry-run: write not applied.",
                    precondition_hash=pre_hash,
                    postcondition_hash=expected_post_hash,
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(action.content, encoding="utf-8")
            actual_post_hash = compute_file_hash(target)
            return ActionResult(
                action.kind,
                action.path,
                True,
                "File written.",
                precondition_hash=pre_hash,
                postcondition_hash=actual_post_hash,
            )

        if action.kind == "delete":
            if self.dry_run:
                return ActionResult(
                    action.kind,
                    action.path,
                    False,
                    "Dry-run: delete not applied.",
                    precondition_hash=pre_hash,
                    postcondition_hash=expected_post_hash,
                )
            if target.exists():
                if target.is_dir():
                    raise ValueError(
                        "Directory deletion is not supported; delete files individually."
                    )
                target.unlink()
            actual_post_hash = compute_file_hash(target)
            return ActionResult(
                action.kind,
                action.path,
                True,
                "File deleted or already absent.",
                precondition_hash=pre_hash,
                postcondition_hash=actual_post_hash,
            )

        raise ValueError(f"Unsupported workspace action: {action.kind}")

    def apply_batch(self, actions: list[WorkspaceAction]) -> list[ActionResult]:
        return [self.apply(action) for action in actions]
