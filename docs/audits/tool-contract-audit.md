# Tool Contract Audit Report

**Date:** 2026-10-31  
**Auditor:** Antigravity Autonomous Agent Engineer  
**Status:** HARDENED & VERIFIED  

---

## 1. Summary of Contract Hardening

All tool contracts in `apps/api/app/tools.py` have been upgraded from lenient (`extra="ignore"`) to strict, deterministic schemas with `extra="forbid"`. The agent control plane strictly rejects any attempt by an advisory model or untrusted input to inject parameters, call unallowlisted commands, or bypass bounding constraints.

---

## 2. Tool-by-Tool Specification

### 1. `repository.inspect`
- **Schema:** `RepositoryInspectArgs` (`extra="forbid"`)
- **Fields:**
  - `repository`: `str | None` (max 500 characters)
  - `query`: `str` (max 1000 characters)
  - `max_files`: `int` (bounded between 1 and 1000, defaults to 500)
- **Validation:** Bounded traversal prevents memory exhaustion; sanitizes extracted code snippets against prompt injection.

### 2. `workspace.plan`
- **Schema:** `WorkspacePlanArgs` (`extra="forbid"`)
- **Fields:**
  - `repository`: `str | None` (max 500 characters)
  - `dry_run`: `bool` (defaults to `True`)
  - `kind`: `Literal["write", "delete"]` (strict enum; any other string rejected)
  - `path`: `str` (bounded between 1 and 500 characters)
  - `content`: `str | None` (capped at 100,000 characters)
- **Validation:** Null bytes, parent directory escapes (`..`), and direct modification of `.git/` or `.env` are rejected.

### 3. `command.run`
- **Schema:** `CommandRunArgs` (`extra="forbid"`)
- **Fields:**
  - `repository`: `str | None` (max 500 characters)
  - `command_id`: `Literal["python.tests", "python.compile", "git.diff.check", "git.status", "git.diff", "python.ruff"]`
  - `extra_args`: `list[str]` (max 20 items, only permitted for `python.compile`)
  - `timeout_seconds`: `float` (strictly bounded: `1.0 <= timeout <= 60.0`)
- **Validation:** Subprocess execution uses `shell=False` and a sanitized environment (`PATH`, `HOME`, `PYTHONUNBUFFERED`, `SYSTEMROOT`). Arbitrary shell strings are strictly impossible.

### 4. `verification.run`
- **Schema:** `VerificationRunArgs` (`extra="forbid"`)
- **Fields:**
  - `repository`: `str | None` (max 500 characters)
  - `expected_files`: `list[str]` (max 50 items)
- **Validation:** Evaluates file presence and `git diff --check` without executing arbitrary test hooks.

---

## 3. Verification & Test Evidence

Tested in `apps/api/tests/test_tool_contracts.py`:
- Injected unknown fields rejected with `Extra inputs are not permitted`.
- Invalid action kinds rejected with `Input should be 'write' or 'delete'`.
- Unallowlisted commands rejected at schema validation.
- Non-positive or out-of-range timeouts rejected with Pydantic boundary errors.
- Valid requests execute cleanly and produce structured `EvidenceRecord` items.
