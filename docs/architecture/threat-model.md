# Security Architecture & Threat Model

**Status:** AUDITED & HARDENED  
**Scope:** Application-Level Execution Boundary, Filesystem Controls, and Command Sandboxing  

---

## 1. Threat Assumptions & Attacker Profile

We assume that:
1. Untrusted software repositories may contain intentionally hostile files, scripts, or commit history.
2. Repository documentation, commit messages, comments, and tests may contain **prompt injection payloads** crafted to manipulate advisory LLM planners.
3. Advisory LLM outputs cannot be trusted as an execution security boundary.
4. An attacker may attempt to trigger path traversal, delete host files, read ambient secrets (e.g., cloud credentials, SSH keys, `.env` files), or execute arbitrary shell commands.

---

## 2. Security Boundaries & Countermeasures

```text
       Untrusted Repo Context / Prompt Payload
                         │
                         ▼
           ┌───────────────────────────┐
           │ Prompt Sanitizer          │  Defangs [System Prompt:], override markers
           └─────────────┬─────────────┘
                         │
                         ▼
           ┌───────────────────────────┐
           │ Strict Schema Validation  │  extra="forbid", bounded types, enums
           └─────────────┬─────────────┘
                         │
                         ▼
           ┌───────────────────────────┐
           │ Fail-Closed Policy Engine │  Allowlisted tools only, risk classification
           └─────────────┬─────────────┘
                         │
                         ▼
           ┌───────────────────────────┐
           │ Operator Approval Gate    │  Mutating changes halt at AWAITING_APPROVAL
           └─────────────┬─────────────┘
                         │
                         ▼
       ┌─────────────────┴─────────────────┐
       ▼                                   ▼
┌───────────────────────────┐ ┌───────────────────────────┐
│ Path Containment Guard    │ │ Shell-Free Command Runner │
│ resolve() + relative_to() │ │ shell=False, strict argv  │
│ Rejects: .., UNC, null,   │ │ Filtered environment      │
│ drive paths, .git, .env   │ │ Process tree termination  │
└───────────────────────────┘ └───────────────────────────┘
```

### 2.1 Filesystem Traversal Defenses
- **Null Byte Injection (`\0`)**: Immediately caught and rejected before filesystem access.
- **Parent Traversal (`../`)**: Normalized via `resolve()` and verified against `target.relative_to(self.root)`.
- **UNC Path Rejection**: Leading `//` or `\\\\` sequences are blocked.
- **Drive Letter Escape**: Absolute Windows drive prefixes (`C:`, `D:`) are blocked.
- **Alternate Data Streams (NTFS)**: Paths containing `:` are rejected to prevent hidden stream writes.
- **Protected File Filtering**: Any path resolving into `.git` or `.env` (case-insensitive) is rejected.

### 2.2 Command Execution Defenses
- **Shell-Free Execution**: Subprocesses invoke fixed argv tuples using `subprocess.Popen(list(argv), shell=False)`.
- **Allowlist Enforcement**: Only pre-registered command IDs are executable (`python.tests`, `python.compile`, `git.diff.check`, `git.status`, `git.diff`, `python.ruff`).
- **Process Tree Cleanup**: Upon hitting the 60s hard timeout, the runner terminates the entire child process tree (`taskkill /F /T /PID` on Windows or `proc.kill()` on Unix) to prevent orphan background processes.
- **Environment Sanitation**: Ambient environment variables are stripped. Only `PATH`, `HOME`, `PYTHONUNBUFFERED`, `SYSTEMROOT`, and `COMSPEC` are passed.

### 2.3 Approval Gate Enforcement
- Any non-dry-run mutating operation (`dry_run=False`) requires explicit operator approval.
- Default `ResumeRequest` requires explicit `approved: true` (`approved` defaults to `False`).
- An approval applies only to the specific intended run and operation.

### 2.4 Documented Sandbox Limitations
> **IMPORTANT:** This repository enforces application-level execution safety, **not** OS-level sandboxing. Subprocesses still run under the host user account. For hostile untrusted code, production deployments should configure container-level isolation (e.g., Docker container with `--read-only`, non-root user, `--network none`, and CPU/memory limits).
