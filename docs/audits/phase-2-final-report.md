# Phase 2 Final Engineering Report: Production-Reliable Autonomous Coding System

**Repository:** `https://github.com/Asterioxer/agentic_software_engineer`  
**Working Branch:** `phase-2-production-reliability`  
**Date:** 2026-10-31  
**Author:** Antigravity Principal Engineering Agent  

---

## 1. Executive Summary & Verified Quality Scoreboard

Phase 2 evolved the autonomous coding prototype into an auditable, crash-consistent, and adversarial-resistant software engineering system. Every claim in this report is backed by deterministic automated test runs and evaluation reports.

### Verified Baseline vs. Final Metrics

| Metric / Check | Baseline (Start of Phase 2) | Final Verified Result (Completion) | Status |
|---|:---:|:---:|:---:|
| **Pytest Unit/Integration Suite** | 41 passed | **58 passed** (+41% expansion) | **PASSED** |
| **Code Coverage (`pytest-cov`)** | 88% | **89%** (1,508 statements, 164 missed) | **PASSED** (Exceeds 85% floor) |
| **Ruff Linter** | 0 errors | **0 errors** (all rules passed) | **PASSED** |
| **Ruff Formatter** | Formatted | **Clean** | **PASSED** |
| **Mypy Type Checking** | Strict (app only) | **Strict (app + tests, 50 files)** | **PASSED** |
| **Next.js Production Build** | Clean | **Compiled successfully (0 type errors)** | **PASSED** |
| **Independent Benchmark Scenarios** | 10 scenarios | **15 real-world scenarios** | **PASSED** |
| **Benchmark Pass Rate** | 100% | **100.0% (15/15 passed)** | **VERIFIED** |
| **Policy Adherence Rate** | 100% | **100.0%** | **VERIFIED** |
| **Truthfulness Rate** | 100% | **100.0% (Zero false success)** | **VERIFIED** |
| **E2E Reproducible Demo** | None | **Demo A (Approved) + Demo B (Honest Refusal)** | **VERIFIED** |

---

## 2. Milestone-by-Milestone Implementation Breakdown

### Milestone Zero: Baseline Audit & Verification
- Established isolated virtual environment (`apps/api/.venv`) resolving Starlette/FastAPI collection conflicts.
- Verified initial checkout against all quality gates and documented in `docs/audits/phase-2-baseline.md`.

### Milestones One & Two: Durable Operation Journal & Crash Consistency
- **Durable Operation Journal (`app/domain.py`, `app/store.py`):** Added `OperationState` enum (`PENDING`, `PREPARED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `INTERRUPTED`, `RECONCILIATION_REQUIRED`, `CANCELLED`) and `JournalOperation` dataclass.
- **SQLite Write-Ahead Logging:** Enabled `PRAGMA journal_mode=WAL;` and 5000ms busy timeout on SQLite connection. Created `operations` table with composite indexes on `run_id` and `idempotency_key`.
- **Deterministic Idempotency Keys:** Formatted as $\text{SHA-256}(\text{run\_id} \parallel \text{step\_id} \parallel \text{input\_hash})[:16]$. Repeated executions detect prior successful records and skip side effects without re-mutating disk.
- **Precondition & Postcondition Hashing:** Computed SHA-256 content hashes before writing to disk.
- **Crash Reconciliation:** On startup or run resumption, `_reconcile_interrupted_operations()` scans for `RUNNING`/`PREPARED` operations, matches current disk content against expected postcondition hashes, reconciles clean writes to `SUCCEEDED`, and flags diverged files as `RECONCILIATION_REQUIRED`.
- **Fault-Injection Tests:** Verified in `tests/test_operation_journal.py` (4 tests).

### Milestone Three: Tool Contract Hardening
- Hardened all tool input schemas in `app/tools.py` with strict Pydantic v2 `extra="forbid"`, bounded string lengths (`max_length`), and `Literal` tool kind enums.
- Prevented injection of undeclared arguments into tool handlers.
- Documented in `docs/audits/tool-contract-audit.md` and verified in `tests/test_tool_contracts.py` (5 tests).

### Milestone Four: Security & Adversarial Hardening
- **Filesystem Traversal Defenses (`app/execution.py`):** Protected `_safe_path` against UNC network shares (`//`), Windows drive roots (`C:`), NTFS alternate data streams (`:`), null bytes (`\0`), and case-insensitive dotfiles (`.git`, `.env`).
- **Process Tree Cleanup (`app/command_runner.py`):** Replaced basic `subprocess.run` with `subprocess.Popen` and added `_kill_process_tree` (`taskkill /F /T /PID` on Windows, `os.killpg` on Unix) to terminate orphaned child processes upon timeout.
- **Fail-Closed API Default (`app/main.py`):** Updated `ResumeRequest` so `approved: bool = Field(default=False)`. Explicit authorization is mandatory to execute mutations.
- Produced comprehensive threat model in `docs/architecture/threat-model.md`.

### Milestone Five: Independent Evaluation Harness V2
- **Eliminated Synthetic Shortcuts:** Refactored `IndependentEvaluator` (`app/evaluation/evaluator.py`) so all scenarios (including policy bypass and honest failure) execute through the real `AgentRun.execute()` pipeline.
- **Dataset Expansion:** Expanded dataset from 10 to 15 real-world scenarios:
  1. `eval-01-success`: Standard coding task in clean workspace
  2. `eval-02-ambiguous`: Underspecified prompt handling
  3. `eval-03-missing-deps`: Nonexistent package dependency detection
  4. `eval-04-invalid-tool-args`: Tool argument boundary validation
  5. `eval-05-tool-timeout`: Command execution hard timeout resilience
  6. `eval-06-api-failures`: Provider fallback to deterministic planner
  7. `eval-07-prompt-injection`: Prompt injection defanging in repo files
  8. `eval-08-policy-bypass`: Malicious tool execution blocked by policy
  9. `eval-09-regression-detection`: Missing expected verification file caught
  10. `eval-10-honest-failure`: Impossible verification criteria honestly refused
  11. `eval-11-crash-recovery`: Interrupted operation reconciled from postcondition
  12. `eval-12-idempotent-replay`: Duplicate execution deduplication via Operation Journal
  13. `eval-13-approval-enforcement`: Unapproved mutation halted in `awaiting_approval`
  14. `eval-14-filesystem-escape`: Path traversal attempt caught and halted
  15. `eval-15-oversized-output`: Context bounds enforced on large files
- Produced machine-readable `evaluation_report.json` and `docs/audits/evaluation-summary.md`.

### Milestone Six: Advanced Verification & Failure Management
- **Syntax Verification (`app/verification.py`):** AST-based Python syntax parsing (`ast.parse`), JSON decoding (`json.loads`), and TOML syntax parsing (`tomllib.loads`).
- **Proof-of-Test Verification:** Inspects AST of test files to verify they contain executable test functions (`test_*`) or test classes (`Test*`) rather than empty placeholders.
- **Clean Diff Verification:** Verified git diff whitespace integrity via `git.diff.check`.
- Verified in `tests/test_verification.py` (5 tests).

### Milestone Seven: Planning & Repository Intelligence
- **Dependency Manifest Parsing (`app/repository_service.py`):** Parses `pyproject.toml`, `requirements.txt`, and `package.json`.
- **Framework Discovery:** Heuristic detection of FastAPI, Flask, Django, Pytest, Next.js, React, Express, Jest.
- **Test-to-Source Mapping:** Heuristic mapping linking source modules to their corresponding test suites (e.g. `src/calc.py` -> `tests/test_calc.py`).
- Verified in `tests/test_repository.py` (3 tests).

### Milestone Eight: API & Database Reliability (Concurrency & Fault Tolerance)
- **Concurrent Resume Lock (`app/runner.py`):** Added thread-safe per-run mutex locking (`_get_run_lock`) preventing race conditions during simultaneous resume requests. Subsequent requests detect `checkpoint.status == COMPLETED` and return the completed response without duplicate side effects.
- **Unhandled 500 Error Masking (`app/main.py`):** Added custom exception handler to sanitize internal server errors and mask tracebacks from API clients while logging full details internally.
- Verified in `tests/test_concurrency.py` (3 tests).

### Milestone Nine: Operator Dashboard Improvements
- **Operation Journal UI:** Added live Operation Journal table in `apps/web/app/page.tsx` displaying operation IDs, tool names, execution states, attempt counts, and recovery/idempotency keys.
- **Repository Intelligence Tab:** Displays detected frameworks (badges), dependency manifests (dependencies, scripts), and test-to-source relationships.
- **15-Scenario Evaluation View:** Real-time benchmark execution view showing pass rate, policy adherence rate, and truthfulness rate across all 15 scenarios.
- Verified with clean Next.js production build (`npm run build`).

### Milestone Ten: Observability & CI Pipeline Hardening
- **CI Workflow (`.github/workflows/ci.yml`):** Configured GitHub Actions to trigger on `phase-2-production-reliability`, running Ruff linting/formatting, strict Mypy across `app` and `tests`, pytest with coverage enforcement (`--cov-fail-under=85`), and the full Evaluation Harness V2.

### Milestone Eleven: End-to-End Real-World Demonstrations
- Implemented `scripts/demo_e2e.py`:
  - **Demo A:** Realistic sample calculator project with Git initialization. Agent plans feature addition, pauses for operator approval, resumes upon sign-off, records durable operations, passes independent verification, and completes.
  - **Demo B:** Impossible verification requirement. Agent honestly halts with `RunStatus.FAILED`, categorizes failure as `validation_failure`, and refuses to claim false success.

---

## 3. Security Boundary & Threat Model

> [!IMPORTANT]
> **Application-Level Containment vs. OS-Level Sandboxing:**
> The controls in this system provide rigorous **application-level containment**:
> - Directory boundary validation (resolving real paths and preventing escapes)
> - Shell-free execution (`shell=False`)
> - Strict command allowlisting (`git diff`, `pytest`, `ruff`)
> - Strict Pydantic argument schemas (`extra="forbid"`)
> - Process tree termination on timeout
>
> These controls **do not** constitute an OS-level sandbox (such as Linux namespaces, cgroups, seccomp, or disposable Docker/Firecracker microVMs). Untrusted third-party code must always be executed within an isolated container or virtual machine.

---

## 4. Known Limitations & Future Work

1. **Host-Level Command Execution:** Subprocess execution relies on host binaries. In production multi-tenant deployments, worker processes should be delegated to ephemeral Linux containers.
2. **Local SQLite Persistence:** The SQLite WAL store is optimized for single-host deployments. Multi-instance horizontal scaling would require distributed persistence (e.g. PostgreSQL).
3. **AST Parser Language Coverage:** Full AST symbol extraction and syntax verification currently cover Python, JSON, and TOML; TypeScript/JavaScript uses regex-based symbol extraction.

---

## 5. Local Run & Verification Instructions

### 1. Run Automated Test Suite & Linters
```powershell
cd apps/api
.\.venv\Scripts\pytest -v --cov=app --cov-report=term-missing
.\.venv\Scripts\ruff check .
.\.venv\Scripts\mypy app tests
```

### 2. Run Independent Evaluation Benchmark V2
```powershell
cd apps/api
.\.venv\Scripts\python -m app.evaluation.evaluator
```

### 3. Run Reproducible End-to-End Demonstrations
```powershell
.\apps\api\.venv\Scripts\python scripts/demo_e2e.py
```

### 4. Build and Run Operator Dashboard
```powershell
cd apps/web
npm install
npm run build
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to inspect the live control plane.
