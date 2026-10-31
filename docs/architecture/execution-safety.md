# Execution Safety

Planning and execution are strictly segregated boundaries.

## Safety Invariants

1. **Dry-Run by Default**:
   All workspace mutations (`kind="write"`, `kind="delete"`) default to dry-run previews (`dry_run=True`). Real filesystem changes require explicit opt-in.
2. **Operator Approval Gate**:
   When real mutations are requested (`dry_run=False`), the agent halts execution at `AWAITING_APPROVAL`. The operator must explicitly inspect the plan and approve via `POST /api/v1/runs/{run_id}/resume`.
3. **Strict Path Containment**:
   Paths are resolved using `resolve()` against the repository root. Any path containing null bytes, path traversal sequences (`../`), or attempting to escape the configured root is rejected with a fatal error.
4. **VCS & Secret Protection**:
   Direct modification of `.git/` internals or environment files (`.env`) is explicitly forbidden.
5. **No Arbitrary Shell**:
   Subprocess execution uses `shell=False` and an explicit command allowlist (`python.tests`, `python.compile`, `git.diff.check`, `git.status`, `git.diff`, `python.ruff`). Command arguments cannot be shell-injected.
6. **Bounded Resource Caps**:
   Commands enforce a hard 60-second timeout and 32 KiB stream truncation limit.
7. **Audit Trail**:
   Every tool call, input argument set, duration, exit code, and stdout/stderr snippet is persisted as structured evidence in the SQLite audit store.

> **Crucial Distinction**: Application-level execution controls are **not** an OS-level sandbox. Host-level isolation (disposable containers or VMs with resource quotas and restricted networking) must be provisioned when running against untrusted repositories.
