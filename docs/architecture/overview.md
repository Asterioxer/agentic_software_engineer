# Architecture Overview

## Control Loop

`User Request → Repository Understanding → Task Decomposition → Execution Plan → Operator Approval → Durable Operation Journaling → Guarded Execution → Multi-Stage Verification → Failure Diagnosis → Evidence-Based Report`

The API accepts a typed `TaskSpec`, retrieves sanitized repository context with dependency and test mappings, decomposes the request into inspectable steps, requests only allowlisted tools, and records persistent step checkpoints and durable Operation Journal records in SQLite Write-Ahead Logging (WAL).

---

## Safety Boundary

The model is advisory, not privileged:
1. Model suggestions must conform to strict Pydantic schemas with `extra="forbid"`.
2. The policy layer authorizes every tool call before invocation.
3. Mutations default to dry-run; real modifications require explicit operator approval.
4. Commands execute shell-free (`shell=False`) with strict timeouts, output limits, and process tree termination (`_kill_process_tree`).
5. Filesystem operations reject path traversal, UNC paths, drive prefixes, and NTFS alternate data streams.
6. Verification independently produces structured evidence and cannot be overridden by model assertions.

> **Important:** This is application-level execution safety, not an OS-level sandbox. Untrusted repositories should be run within disposable containers or VMs.

---

## Execution Lifecycle

```text
       ┌──────────┐
       │  INTAKE  │
       └────┬─────┘
            ▼
       ┌────────────────────────┐
       │ CRASH RECONCILIATION   ├──────────────────────────┐
       └────┬───────────────────┘                          │
            ▼ (clean / reconciled)                         ▼ (corrupted / hash diverged)
       ┌──────────┐                             ┌───────────────────────────┐
       │ PLANNING │                             │  RECONCILIATION_REQUIRED  │
       └────┬─────┘                             └───────────────────────────┘
            │
            ├──────────────────────────────────────────┐
            ▼ (if mutating action & not auto-approved) │
 ┌──────────────────────┐                             │
 │  AWAITING_APPROVAL   │                             │
 └──────────┬───────────┘                             │
            │ (approved via /resume with run lock)    │
            ▼                                         ▼
       ┌──────────┐                            ┌────────────┐
       │EXECUTING ├───────────────────────────▶│   FAILED   │
       └────┬─────┘ (unrecoverable / budget 0) └────────────┘
            ▼                                         ▲
       ┌──────────┐                                   │
       │VERIFYING ├───────────────────────────────────┤
       └────┬─────┘ (verification gate failed)        │
            ▼                                         │
       ┌──────────┐                                   │
       │REFLECTING├───────────────────────────────────┘
       └────┬─────┘
            ▼ (all gates green)
       ┌──────────┐
       │COMPLETED │
       └──────────┘
```

---

## Core Subsystems

1. **Repository Intelligence & Sanitized Code Context (`repository.py`, `code_context.py`, `repository_service.py`)**:
   Bounded file traversal, symbol extraction (Python & TypeScript), dependency manifest parsing (`pyproject.toml`, `requirements.txt`, `package.json`), framework discovery (FastAPI, Pytest, Next.js), test-to-source file mapping, and prompt-injection defanging.

2. **Durable Operation Journal & Persistent Checkpoint Store (`store.py`, `domain.py`)**:
   Thread-safe SQLite storage with Write-Ahead Logging (WAL) and 5000ms busy timeout. Tracks operations with operation-level idempotency keys, precondition/postcondition SHA-256 hashes, and automatic crash reconciliation.

3. **Guardrails & Execution Boundary (`policy.py`, `execution.py`, `command_runner.py`, `tools.py`)**:
   Strict tool allowlist, path traversal defenses (UNC, drive prefix, NTFS stream, null-byte checks), process tree termination on timeout (`taskkill /F /T` on Windows), and fail-closed operator approval defaults.

4. **Multi-Stage Verification Pipeline (`verification.py`, `verification_pipeline.py`)**:
   Multi-stage deterministic checks:
   - File existence and workspace containment.
   - AST-based Python syntax parsing (`ast.parse`), JSON decoding check (`json.loads`), and TOML syntax check (`tomllib.loads`).
   - Proof-of-test verification (ensuring test files define executable `test_*` functions or `Test*` classes).
   - Git diff whitespace integrity check.

5. **Failure Classification & Reflection (`reflection.py`)**:
   Categorizes errors (`POLICY_VIOLATION`, `TIMEOUT`, `SYNTAX_ERROR`, `DEPENDENCY_MISSING`, `VALIDATION_FAILURE`, `RECOVERY_REQUIRED`) with bounded retry budgets and targeted recovery guidance.

6. **Independent Evaluation Harness V2 (`evaluation/`)**:
   15-scenario benchmark suite evaluating task completion, policy adherence, truthfulness, crash recovery, idempotent replay, approval enforcement, and filesystem boundary checks without letting the agent grade itself.
