# Execution Safety & Deterministic Boundaries

Planning and execution are strictly segregated boundaries. The model is advisory; execution is deterministic and fail-closed.

## Core Safety Invariants

1. **Dry-Run by Default**:
   All workspace mutations (`kind="write"`, `kind="delete"`) default to dry-run previews (`dry_run=True`). Real filesystem changes require explicit opt-in.

2. **Cryptographic Operator Approval Gate**:
   When real mutations are requested (`dry_run=False`), the agent halts execution at `AWAITING_APPROVAL`.
   - The approval request computes a deterministic cryptographic fingerprint:
     $$\text{Fingerprint} = \text{SHA-256}(\text{JSON-serialized Plan Steps} \parallel \text{Unified Diff})$$
   - Resumption requires passing the exact `expected_fingerprint`. If the plan, step order, preconditions, or workspace state diverge prior to approval, the approval is invalidated (`APPROVAL_INVALIDATED`), and execution halts.
   - Operators can explicitly reject mutations via `approved=False` or API `POST /api/v1/runs/{run_id}/resume`, terminating the run safely.

3. **Anti-Cycling Defense & Disciplined Self-Correction**:
   The `SelfCorrectionEngine` maintains an immutable record of attempted repair strategies.
   - Each failure generates a deterministic signature:
     $$\text{Signature} = \text{SHA-256}(\text{category} \parallel \text{error message} \parallel \text{target file})$$
   - If an automated repair proposes an identical patch for the same failure signature, anti-cycling triggers immediately, classifying the failure as `STRATEGY_LOOP` to halt infinite repair loops.
   - All proposed repair code is gated by the AST Security Critic before application.

4. **Clean Cancellation & Timeout Propagation**:
   - Operators can abort any active run via `POST /api/v1/runs/{run_id}/cancel`, CLI `python -m app.cli cancel`, or WebSocket action `cancel`.
   - Cancellation requests immediately mark checkpoints `cancellation_requested=True`, skip pending steps, update Operation Journal entries to `CANCELLED`, and fail the run cleanly without orphaned processes.
   - Subprocess executions enforce a strict 60-second bounded timeout with recursive process tree termination (`_kill_process_tree`).

5. **Strict Path Containment**:
   Paths are resolved using `resolve()` against the repository root. Any path containing null bytes, path traversal sequences (`../`), symlink escapes, drive prefixes, UNC paths, or NTFS alternate data streams is rejected with a fatal error.

6. **VCS & Secret Protection**:
   Direct modification of `.git/` internals or sensitive environment files (`.env`, `.env.*`) is explicitly forbidden.

7. **No Arbitrary Shell**:
   Subprocess execution uses `shell=False` and an explicit command allowlist (`python.tests`, `python.compile`, `git.diff.check`, `git.status`, `git.diff`, `python.ruff`). Command arguments cannot be shell-injected.

8. **Bounded Resource Caps**:
   Commands enforce a hard 60-second timeout and 32 KiB stream truncation limit.

9. **Durable Operation Journaling**:
   Every stateful operation generates an idempotency key and condition hash in SQLite WAL mode. Completed operations are never blindly re-executed upon task resumption (idempotent replay).

> **Crucial Distinction**: Application-level execution controls are **not** an OS-level sandbox. Host-level isolation (disposable containers or VMs with resource quotas and restricted networking) must be provisioned when running against untrusted repositories.
