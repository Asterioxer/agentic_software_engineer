# Phase 2 Baseline Audit & Reliability Assessment

**Date:** 2026-10-31  
**Working Branch:** `phase-2-production-reliability`  
**Repository:** `Asterioxer/agentic_software_engineer`  
**Auditor:** Antigravity Autonomous Agent Engineer  

---

## 1. Executive Summary

A comprehensive independent audit of the repository checkout was performed before initiating any Phase 2 implementation. The codebase contains a functional, well-structured foundation comprising a FastAPI control plane, an SQLite persistence store, a bounded runner, deterministic planning, tool guardrails, an independent evaluation harness, and a Next.js operator dashboard.

All 41 existing test cases pass, test coverage stands at 88%, static type-checking with Mypy is 100% clean under `strict = true`, Ruff linting and formatting are clean, and the Next.js frontend builds without errors.

However, treating this system as a production-grade autonomous engineer reveals critical vulnerabilities in **crash consistency, idempotency, tool schema strictness, adversarial command execution, evaluation scenario validity, and operation-level durability**.

---

## 2. Verified Baseline Metrics (Current Checkout)

| Check | Tool / Command | Verified Result | Status |
|---|---|---:|---|
| **Pytest** | `pytest -v` | 41 passed, 0 failed | VERIFIED |
| **Code Coverage** | `pytest --cov=app` | 88% (1,100 stmts, 127 miss) | VERIFIED |
| **Linter** | `ruff check .` | 0 errors | VERIFIED |
| **Formatter** | `ruff format --check .` | 47 files clean | VERIFIED |
| **Type Checker** | `mypy app` | Strict passed (25 files) | VERIFIED |
| **Frontend Build** | `next build` | 4/4 static pages generated | VERIFIED |
| **Git Working Tree** | `git status` | Clean, branched to `phase-2-production-reliability` | VERIFIED |

---

## 3. Detailed Component Audit & Gap Analysis

| Area | Current Implementation | Verified? | Remaining Weakness | Priority |
|---|---|:---:|---|:---:|
| **Execution Lifecycle** | Run-level loop with step statuses (`pending`, `running`, `completed`, `failed`). | YES | State is saved *after* tool execution. A crash immediately post-mutation causes step re-execution upon resume, potentially duplicating side effects. No two-phase commit. | **P0** |
| **Persistence** | SQLite `runs`, `events`, `evidence` tables. | YES | Lacks a dedicated `operations` table (Operation Journal). Does not record operation state transitions, idempotency keys, or input/output checksums. SQLite WAL mode not enabled. | **P0** |
| **Recovery** | Resumes from `current_step_index`. | YES | Coarse-grained. Cannot distinguish between an operation that never started, completed successfully, failed, or was interrupted in-flight. | **P0** |
| **Idempotency** | Partial (checks if step status is `COMPLETED`). | PARTIAL | If process dies during/after write but before checkpoint save, step re-runs. No precondition/postcondition file hash comparison or idempotency keys. Duplicate API requests are not deduplicated. | **P0** |
| **Security** | Application-level path normalization and command allowlist. | YES | `extra="ignore"` in tool schemas accepts unknown parameters. Command runner does not kill child process trees upon timeout. Default `approved=True` in `ResumeRequest` could cause accidental approvals. | **P0** |
| **Tool Contracts** | 4 tools (`repository.inspect`, `workspace.plan`, `command.run`, `verification.run`) with Pydantic schemas. | YES | Schemas use `extra="ignore"`, permitting injected arbitrary fields. Types allow unconstrained strings instead of strict literals/enums (`kind`, `command_id`). | **P0** |
| **Planning** | Fixed 4-step deterministic sequence with inputs/outputs. | YES | Lacks dependency manifest parsing (pyproject.toml, package.json), test-to-source mapping, and blast-radius estimation. | **P1** |
| **Verification** | Checks file presence and `git diff --check`. | YES | Does not assert pre/post file content hashes, AST syntax validity, or test execution proofs. | **P1** |
| **Evaluation** | 10 benchmark scenarios, independent evaluator. | YES | Scenarios 8 and 10 manually invoke policy/verification functions rather than driving the full agent lifecycle. Missing scenarios for crash recovery, duplicate execution, and process cleanup. | **P1** |
| **Dashboard** | Next.js 15 app with 4 tabs (Execution, Repo, Diff, Eval). | YES | Approval drawer does not display exact pre/post diffs or operation journal records. Relies on polling rather than streaming or rich state inspection. | **P2** |
| **API** | FastAPI endpoints for runs, resume, diff, advisory, eval. | YES | No request deduplication. Concurrent writes to SQLite without WAL mode can lock the database. | **P1** |
| **CI** | GitHub Actions workflow for lint, mypy, pytest, and web build. | YES | Does not run security scanning, coverage threshold enforcement, or evaluation benchmark regression tests. | **P1** |

---

## 4. Prioritised Milestone Implementation Plan

- **Milestone 1: Execution Integrity & Durable Operation Journal (P0)**
  - Implement durable Operation Journal (`OperationState`: `PENDING`, `PREPARED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `INTERRUPTED`, `RECONCILIATION_REQUIRED`, `CANCELLED`).
  - Implement two-phase state transitions in SQLite: log operation preparation before execution; transition to running; record outcome and postconditions.
  - Enable SQLite Write-Ahead Logging (WAL) and busy timeout.
  - Implement crash consistency and recovery logic.

- **Milestone 2: Operation Idempotency & Reconciliation (P0)**
  - Operation-level idempotency keys derived from normalized run ID, step ID, and input hash.
  - Precondition and postcondition verification for filesystem mutations (SHA-256 content hashes).
  - Explicit reconciliation for interrupted operations: if postcondition is already met, mark as reconciled rather than re-executing.
  - Fault-injection testing across execution boundaries.

- **Milestone 3: Tool Contract Hardening (P0)**
  - Enforce `extra="forbid"` on all tool argument schemas.
  - Strict Enum/Literal validation for `kind` (`write`, `delete`), `command_id`, and bounded limits.
  - Reject unexpected parameters, invalid paths, and dangerous arguments.

- **Milestone 4: Security & Adversarial Hardening (P0)**
  - Process tree termination on command timeout (`taskkill` / `SIGTERM`).
  - Safe API defaults: `ResumeRequest` must require explicit `approved: bool` without default `True`.
  - Advanced path containment (handling UNC paths, alternate data streams, and case sensitivity).
  - Configurable container execution adapter specification.

- **Milestone 5: Real Evaluation Harness V2 (P1)**
  - Rebuild evaluation scenarios so all scenarios drive the real agent lifecycle without manual shortcut calls.
  - Expand benchmark coverage to 15+ scenarios (including crash recovery, duplicate execution, filesystem escape, truthfulness).
  - Generate multi-dimensional evaluation report (`evaluation_report.json` and `evaluation_summary.md`).

- **Milestone 6: Advanced Verification & Failure Management (P1)**
  - Precondition/postcondition content verification.
  - Structured failure categorization with fine-grained error codes.
  - Proof of test execution and regression defense.

- **Milestone 7: Planning & Repository Intelligence (P1)**
  - Dependency manifest detection (`pyproject.toml`, `package.json`, `Cargo.toml`).
  - Test-to-source mapping and blast radius estimation.

- **Milestone 8: API & Concurrency Hardening (P1)**
  - Concurrent request stress testing on SQLite.
  - Safe error masking preventing internal path disclosures.

- **Milestone 9: Operator Dashboard Improvements (P2)**
  - Enhance approval interface with exact diffs, risk score, and reversibility.
  - Add Operation Journal viewer and scenario breakdown.

- **Milestone 10: Observability & CI (P1)**
  - Structured execution tracing with correlation IDs.
  - Enhanced GitHub Actions workflow with coverage gating.

- **Milestone 11: End-to-End Real-World Demonstrations (P1)**
  - Demonstration 1: Successful bounded engineering task on a real Python calculator project.
  - Demonstration 2: Failure / adversarial test proving truthful failure reporting.

- **Milestone 12: Documentation & Final Report (P1)**
  - Complete architecture updates, recovery guides, threat model, and final Phase 2 delivery report.
