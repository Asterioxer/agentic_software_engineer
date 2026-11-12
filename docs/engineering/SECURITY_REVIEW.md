# Security Review & Trust Boundary Audit

**Date:** 2026-11-09  
**Scope:** `apps/api`, `apps/web`, tool contracts, execution layer, approval gate, patch applier.

---

## 1. Threat Model & Trust Boundaries

```
[ Untrusted User / Repository Input ]
                │
                ▼
      ┌──────────────────┐
      │   Pydantic AST   │  <-- Schema Validation (extra="forbid")
      └─────────┬────────┘
                │
                ▼
      ┌──────────────────┐
      │   Policy Layer   │  <-- Tool Allowlist & Approval Gate
      └─────────┬────────┘
                │
                ▼
      ┌──────────────────┐
      │ Patch & Exec     │  <-- Path Traversal, Symlinks, .git, .env Defenses
      └─────────┬────────┘
                │
                ▼
      ┌──────────────────┐
      │  Subprocess Exec │  <-- shell=False, Allowlisted Commands, Resource Caps
      └──────────────────┘
```

---

## 2. Identified Vulnerabilities & Hardening Status

### VULN-01: PatchApplier Path Traversal & VCS File Poisoning
- **Component:** `apps/api/app/patch.py` (`PatchApplier._safe_target`)
- **Severity:** CRITICAL
- **Status:** **RESOLVED & VERIFIED**
- **Issue:** Unified diff target paths were not checked for `.git/` directory prefixes, `.env` files, null bytes (`\0`), UNC paths (`//share`), or drive prefixes (`C:`). An attacker could construct a patch modifying `.git/hooks/pre-commit` or `.env` files.
- **Remediation:** Enforced strict sanitization in `PatchApplier`: rejects null bytes, UNC paths, drive prefixes, alternate data streams, `.git`, `.env`, and un-resolved symlink writes.
- **Verification Tests:** `apps/api/tests/test_patch_security.py` (5 tests passing), `eval-24-vcs-file-patch-defense` (PASS).

### VULN-02: Time-of-Check to Time-of-Use (TOCTOU) in Approval Resumption
- **Component:** `apps/api/app/runner.py` (`resume_run`, `AgentRun.execute`)
- **Severity:** HIGH
- **Status:** **RESOLVED & VERIFIED**
- **Issue:** The approval fingerprint checks `plan_fingerprint = SHA-256(plan || diff)`. However, if the target file on disk is modified by a concurrent process after approval was requested but before `/resume` is called, the patch is applied against an unverified base file.
- **Remediation:** Bound `workspace_pre_state_hash` of all mutation target files at approval request time in `ApprovalRequest`. On resumption, verifies that current disk hashes match the pre-state hash; aborts immediately with `FailureCategory.APPROVAL_INVALIDATED` upon any divergence.
- **Verification Tests:** `apps/api/tests/test_toctou_defense.py` (PASS), `eval-21-toctou-workspace-defense` (PASS).

### VULN-03: Stale Approval Replay / Lack of Expiration (TTL)
- **Component:** `apps/api/app/domain.py` (`ApprovalRequest`), `apps/api/app/runner.py`
- **Severity:** MEDIUM
- **Status:** **RESOLVED & VERIFIED**
- **Issue:** Approval requests had no expiration time, permitting replay of ancient approvals against drifted workspaces.
- **Remediation:** Introduced `expires_at` (default TTL: 3600 seconds) in `ApprovalRequest`. Resumption attempts after expiration are rejected with `FailureCategory.APPROVAL_INVALIDATED`.
- **Verification Tests:** `apps/api/tests/test_approval_ttl.py` (PASS), `eval-22-approval-expiration-ttl` (PASS).

### VULN-04: Symlink / Junction Traversal Overwrites
- **Component:** `apps/api/app/execution.py` & `apps/api/app/patch.py`
- **Severity:** HIGH
- **Status:** **RESOLVED & VERIFIED**
- **Issue:** Overwriting existing symlinks or writing into symlinked directories could bypass path containment on systems supporting symbolic links or NTFS directory junctions.
- **Remediation:** Checked un-resolved targets with `unresolved.is_symlink()` prior to path resolution; verified ancestor containment to ensure symlinks cannot escape the workspace root.
- **Verification Tests:** `apps/api/tests/test_patch_security.py::test_patch_applier_rejects_symlink_overwrite` (PASS), `eval-23-symlink-traversal-defense` (PASS).

---

## 3. Residual Risks & Operational Guidance
1. **Application-Level vs. OS Sandbox:** Application-level controls in Python cannot provide hard kernel-level isolation (e.g. against zero-day CPython vulnerabilities). Host containers (Docker / Firecracker microVMs) must enclose the API when evaluating untrusted third-party code.
2. **Subprocess Resource Limits:** On Windows, subprocess CPU limits rely on process job objects and timeouts rather than cgroups. Hard timeouts (`timeout_seconds <= 60.0`) are enforced to kill process trees recursively.
