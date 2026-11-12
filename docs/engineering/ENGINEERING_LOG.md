# Engineering Log & Audit Trail

---

## [2026-11-09] Baseline Verification & System Audit
- Verified commit `b6ab5cf`: 152 Pytest unit & integration tests passing with 89% coverage.
- Verified 20 evaluation benchmark scenarios passing with 100% policy adherence and 100% truthfulness.
- Verified Ruff linter and formatter (116 files clean).
- Verified strict Mypy (95 files clean, 0 errors).
- Verified Next.js 15 production build (compiled & bundled in 1.8s).
- Initialized persistent engineering memory artifacts in `docs/engineering/`.
- Conducted deep vulnerability audit across `PatchApplier`, `WorkspaceExecutor`, and `resume_run`.

---

## [2026-11-09] Discovered Architectural & Security Weaknesses
1. **PatchApplier Path Containment Gap:** `PatchApplier._safe_target` did not check for `.git/` hooks, `.env` files, null bytes, UNC paths, or symlink containment, allowing potential malicious patch application to repository control files.
2. **Time-of-Check to Time-of-Use (TOCTOU) in Approval Gate:** `resume_run` validated `plan_fingerprint` but did not verify that target files on disk remained unmodified between approval request and resumption.
3. **Approval Replay & Missing Expiration (TTL):** Approvals had no expiration timestamp (`expires_at`), allowing stale approvals to be replayed indefinitely.
4. **CodeGraph Relative Import Blindspot & Missing Cycle Detection:** Python relative imports (`from .domain import PlanStep`) were dropped during edge resolution, and import cycles were not detected.

---

## [2026-11-12] Security Hardening & Benchmark Expansion Complete
- **PatchApplier & WorkspaceExecutor Hardening (VULN-01, VULN-04):**
  - Reject null bytes, UNC paths, drive letters, NTFS alternate data streams, `.git` internals, `.env` configuration files, and direct/ancestor symlink escapes.
  - Implemented pre-resolution symlink checks (`unresolved.is_symlink()`) to prevent symlink following before resolution.
- **TOCTOU Pre-State Hash Binding (VULN-02):**
  - Added `workspace_pre_state_hash`, `target_files`, and `expires_at` to `ApprovalRequest`.
  - Extracted all plan mutation target files across `workspace.plan` and `workspace.patch`.
  - Enforced dual verification of workspace pre-state at both `resume_run` entry gate and `AgentRun.execute` mutation authorization step.
- **Approval Expiration TTL (VULN-03):**
  - Bound approval requests with default 1-hour TTL (`expires_at`).
  - Resumption attempts on expired requests are rejected with `FailureCategory.APPROVAL_INVALIDATED`.
- **CodeGraph Intelligence Enhancements:**
  - Added package-relative Python import resolution handling `node.level > 0` and `__init__.py` package mappings.
  - Implemented `detect_cycles() -> list[list[str]]` DFS cycle discovery with canonical rotation deduplication.
  - Implemented `find_orphan_files() -> list[str]` with entrypoint and test exclusion filters.
- **Evaluation Benchmark Suite V3:**
  - Expanded from 20 to 25 reproducible scenarios (`eval-21` through `eval-25`).
  - 100% pass rate: 25/25 scenarios passed.
  - 100% policy adherence rate.
  - 100% truthfulness rate (no false success claims).
- **Quality Gates Verified:**
  - Pytest: 161 passed in 79s (88% code coverage).
  - Strict Mypy: 99 source files clean (0 errors).
  - Ruff: 127 files cleanly linted and formatted (0 errors).
  - Next.js 15: production build compiled and bundled in 4.7s.
