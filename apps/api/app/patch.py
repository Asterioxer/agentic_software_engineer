from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .execution import compute_file_hash


@dataclass
class PatchHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)


@dataclass
class FilePatch:
    source_path: str
    target_path: str
    hunks: list[PatchHunk] = field(default_factory=list)


@dataclass
class PatchResult:
    applied: bool
    modified_files: list[str]
    file_hashes: dict[str, dict[str, str]]
    error: str | None = None
    detail: str = ""


HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")


def parse_unified_diff(diff_text: str) -> list[FilePatch]:
    """Parse unified diff format into structured FilePatch and PatchHunk records."""
    patches: list[FilePatch] = []
    current_patch: FilePatch | None = None
    current_hunk: PatchHunk | None = None

    lines = diff_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("--- "):
            # Start of a new file patch header
            src = line[4:].strip().removeprefix("a/").removeprefix("b/")
            target = src
            # Check next line for +++
            if i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
                i += 1
                target = lines[i][4:].strip().removeprefix("a/").removeprefix("b/")

            current_patch = FilePatch(source_path=src, target_path=target)
            patches.append(current_patch)
            current_hunk = None
            i += 1
            continue

        if line.startswith("@@"):
            match = HUNK_HEADER_RE.match(line)
            if match and current_patch:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1
                current_hunk = PatchHunk(old_start, old_count, new_start, new_count)
                current_patch.hunks.append(current_hunk)
            i += 1
            continue

        if current_hunk is not None:
            if line.startswith(("+", "-", " ")) or line == "":
                current_hunk.lines.append(line)
            elif line.startswith("\\ No newline"):
                # Ignore no newline annotation
                pass
            else:
                # End of hunk
                current_hunk = None

        i += 1

    return patches


def apply_hunks_to_lines(
    original_lines: list[str], hunks: list[PatchHunk]
) -> tuple[bool, list[str], str]:
    """Apply a list of hunks to original lines. Returns (success, new_lines, error_message)."""
    result = list(original_lines)
    offset = 0

    for hunk_idx, hunk in enumerate(hunks):
        target_idx = (hunk.old_start - 1) + offset

        # Validate context & deletions against original lines
        orig_slice_idx = target_idx
        expected_matches: list[str] = []
        for hline in hunk.lines:
            if hline.startswith((" ", "-")):
                expected_matches.append(hline[1:])

        # Verify context match
        for match_offset, expected_line in enumerate(expected_matches):
            check_idx = orig_slice_idx + match_offset
            if check_idx < 0 or check_idx >= len(result):
                return (
                    False,
                    original_lines,
                    f"Hunk {hunk_idx + 1} out of bounds at line {check_idx + 1}",
                )
            if (
                result[check_idx] != expected_line
                and result[check_idx].strip() != expected_line.strip()
            ):
                return (
                    False,
                    original_lines,
                    f"Hunk {hunk_idx + 1} mismatch at line {check_idx + 1}: expected '{expected_line}', found '{result[check_idx]}'",
                )

        # Apply substitutions
        new_chunk: list[str] = []
        remove_count = 0
        for hline in hunk.lines:
            if hline.startswith(" "):
                new_chunk.append(hline[1:])
                remove_count += 1
            elif hline.startswith("-"):
                remove_count += 1
            elif hline.startswith("+"):
                new_chunk.append(hline[1:])

        result[target_idx : target_idx + remove_count] = new_chunk
        offset += len(new_chunk) - remove_count

    return True, result, ""


class PatchApplier:
    """Atomic multi-file unified diff applier with boundary protection and condition hashing."""

    def __init__(self, root: str, dry_run: bool = True) -> None:
        self.root = Path(root).resolve()
        self.dry_run = dry_run

    def _safe_target(self, relative_path: str) -> Path:
        normalized = relative_path.replace("\\", "/").strip().lstrip("/")
        if not normalized or normalized.startswith(("/", "\\")) or ".." in normalized.split("/"):
            raise ValueError(f"Path traversal attempted in patch target: {relative_path}")
        target = (self.root / normalized).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"Target '{relative_path}' escapes workspace boundary {self.root}")
        return target

    def apply_diff(self, diff_text: str) -> PatchResult:
        """Atomically apply a unified diff. Rolls back completely if any hunk fails."""
        patches = parse_unified_diff(diff_text)
        if not patches:
            return PatchResult(
                applied=False,
                modified_files=[],
                file_hashes={},
                error="No valid file patches found in unified diff.",
            )

        staged_changes: dict[
            Path, tuple[str, str, str]
        ] = {}  # target -> (new_content, pre_hash, post_hash)

        # Phase 1: Dry-run and validate all patches
        for patch in patches:
            try:
                target = self._safe_target(patch.target_path)
            except ValueError as exc:
                return PatchResult(
                    applied=False,
                    modified_files=[],
                    file_hashes={},
                    error=str(exc),
                )

            pre_hash = compute_file_hash(target)
            if target.is_file():
                orig_text = target.read_text(encoding="utf-8")
                orig_lines = orig_text.splitlines()
            else:
                orig_lines = []

            ok, new_lines, err = apply_hunks_to_lines(orig_lines, patch.hunks)
            if not ok:
                return PatchResult(
                    applied=False,
                    modified_files=[],
                    file_hashes={},
                    error=f"Failed to apply patch to {patch.target_path}: {err}",
                )

            new_content = "\n".join(new_lines)
            if new_lines:
                new_content += "\n"

            import hashlib

            post_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()
            staged_changes[target] = (new_content, pre_hash, post_hash)

        # Record file hashes
        hashes_report: dict[str, dict[str, str]] = {}
        modified_list: list[str] = []

        for target, (_, pre, post) in staged_changes.items():
            rel_str = str(target.relative_to(self.root)).replace("\\", "/")
            modified_list.append(rel_str)
            hashes_report[rel_str] = {"precondition": pre, "postcondition": post}

        if self.dry_run:
            return PatchResult(
                applied=False,
                modified_files=modified_list,
                file_hashes=hashes_report,
                detail=f"Dry-run: validated {len(staged_changes)} file patch(es) cleanly.",
            )

        # Phase 2: Apply all changes to disk
        for target, (content, _, _) in staged_changes.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        return PatchResult(
            applied=True,
            modified_files=modified_list,
            file_hashes=hashes_report,
            detail=f"Applied {len(staged_changes)} file patch(es) atomically.",
        )
