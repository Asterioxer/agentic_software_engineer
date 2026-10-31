# Agent Execution Lifecycle

The agent executes through a deterministic, auditable multi-phase pipeline:

```text
User Request → Crash Reconciliation → Repository Understanding → Task Decomposition → Execution Plan → Operator Approval Gate → Operation Journaling → Guarded Execution → Multi-Stage Verification → Failure Diagnosis & Reflection → Evidence-Based Report
```

---

## Detailed Lifecycle Phases

### 1. Intake & Checkpoint Initialization
- Accepts a typed `TaskSpec` with title, description, constraints, repository root, `dry_run` flag, `auto_approve` flag, `expected_files` list, and `max_retries`.
- Generates a unique `run_id` and records the initial state in SQLite with Write-Ahead Logging (WAL).

### 2. Automatic Crash Reconciliation
- Scans the SQLite `operations` table for any operations from prior invocations left in `PREPARED` or `RUNNING` state.
- Inspects disk state against expected `precondition_hash` and `postcondition_hash`.
- Reconciles clean mutations to `SUCCEEDED` without re-applying side effects.
- If unrecoverable divergence is detected, transitions immediately to `RECONCILIATION_REQUIRED` and demands operator intervention.

### 3. Repository Intelligence & Context Indexing
- Traverses the repository up to a bounded 500 files, ignoring build and package directories.
- Parses dependency manifests (`pyproject.toml`, `requirements.txt`, `package.json`).
- Detects development frameworks and test runners (FastAPI, Pytest, Next.js, React).
- Maps source files to candidate test files for targeted verification.
- Sanitizes file contents to defang embedded prompt injection markers (`System Prompt:`, `Ignore previous instructions`).
- Extracts Python and TypeScript symbol signatures to rank relevant code snippets.

### 4. Task Decomposition & Planning
- Constructs an inspectable, typed list of `PlanStep` objects.
- Each step defines:
  - `id`: Unique step identifier
  - `inputs`: Explicit input parameters
  - `expected_outputs`: Expected artifacts or responses
  - `validation_criteria`: Concrete pass criteria
  - `requires_approval`: Flag denoting whether real mutation requires operator approval

### 5. Operator Approval Gate
- If a step performs real mutations (`dry_run=False`) and `auto_approve=False`, execution transitions to `AWAITING_APPROVAL`.
- Execution halts safely and can be resumed at any point via `POST /api/v1/runs/{run_id}/resume`.
- Resumption is protected by a thread-safe mutex lock (`_get_run_lock`) preventing race conditions from concurrent resume calls.

### 6. Durable Operation Journaling & Idempotency Check
- Before tool invocation, computes:
  - `input_hash = sha256(tool_args)[:16]`
  - `idempotency_key = sha256(run_id:step_id:input_hash)[:16]`
- Queries SQLite for an existing operation with matching `idempotency_key`. If already `SUCCEEDED`, skips execution and reuses the cached output.
- Precomputes SHA-256 `precondition_hash` and `postcondition_hash` for file mutations.
- Inserts a journal record in `PREPARED` state, then updates to `RUNNING`.

### 7. Guarded Tool Execution
- Step tools are validated against `ToolPolicy.ALLOWED_TOOLS`.
- Arguments are validated against strict Pydantic schemas with `extra="forbid"`.
- Execution occurs through `ToolRegistry.execute_guarded`:
  - Enforces execution timeouts and output bounding.
  - Subprocess commands execute shell-free (`shell=False`) with process tree cleanup (`_kill_process_tree`) on timeout.
  - Filesystem actions enforce workspace containment and reject UNC paths, drive prefixes, and NTFS streams.
- Upon completion, updates Operation Journal to `SUCCEEDED` (or `FAILED`) with execution metrics.

### 8. Multi-Stage Independent Verification
- Execution success is determined **exclusively** by independent deterministic checks, never by model self-evaluation.
- Multi-stage checks include:
  - Mandatory plan and allowlist checks (`plan_exists`, `repository_context`, `tool_allowlist`).
  - File existence and workspace containment for `expected_files`.
  - Language syntax validation: Python AST syntax (`ast.parse`), JSON decoding (`json.loads`), TOML syntax (`tomllib.loads`).
  - Proof-of-test verification (ensuring test files define executable `test_*` functions or `Test*` classes).
  - Clean Git diff verification (`git.diff.check` with no whitespace errors).

### 9. Failure Diagnosis & Bounded Reflection
- If any step or verification check fails, errors are classified into categories:
  - `POLICY_VIOLATION` (fatal, non-recoverable)
  - `TIMEOUT` (recoverable with scoped arguments)
  - `SYNTAX_ERROR` (recoverable with patch fix)
  - `DEPENDENCY_MISSING` (fatal, admits missing environment dependencies)
  - `VALIDATION_FAILURE` (recoverable within retry budget)
  - `RECOVERY_REQUIRED` (fatal, requires manual disk reconciliation)
- If recoverable and `retry_count < max_retries`, the agent retries bounded actions.
- If exhausted or fatal, transitions cleanly to `FAILED` with an evidence-based diagnosis.

### 10. Evidence Report
- Returns the complete run checkpoint, durable operations journal, tool execution logs, independent check results, and execution timeline.
