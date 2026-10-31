# Agent Execution Lifecycle

The agent executes through a deterministic, auditable multi-phase pipeline:

```text
User Request → Repository Context → Task Decomposition → Execution Plan → Operator Approval → Guarded Execution → Independent Verification → Failure Diagnosis → Evidence-Based Report
```

## Detailed Lifecycle Phases

### 1. Intake
- Accepts a typed `TaskSpec` with title, description, constraints, repository root, `dry_run` flag, and `max_retries`.
- Generates a unique `run_id` and records the initial state in SQLite.

### 2. Repository Understanding
- Traverses repository up to a bounded 500 files, ignoring build and package directories.
- Sanitizes file contents to defang embedded prompt injection markers (`System Prompt:`, `Ignore previous instructions`).
- Extracts Python and TypeScript symbol signatures to rank relevant code snippets.

### 3. Task Decomposition & Planning
- Constructs an inspectable, typed list of `PlanStep` objects.
- Each step defines:
  - `id`: Unique step identifier
  - `inputs`: Explicit input parameters
  - `expected_outputs`: Expected artifacts or responses
  - `validation_criteria`: Concrete pass criteria
  - `requires_approval`: Flag denoting whether real mutation requires operator approval

### 4. Operator Approval Gate
- If a step performs real mutations (`dry_run=False`) and `auto_approve=False`, execution transitions to `AWAITING_APPROVAL`.
- Execution halts safely and can be resumed at any point via `POST /api/v1/runs/{run_id}/resume`.

### 5. Guarded Tool Execution
- Step tools are validated against `ToolPolicy.ALLOWED_TOOLS`.
- Arguments are validated against strict Pydantic schemas.
- Execution occurs through `ToolRegistry.execute_guarded`, tracking timing and capturing evidence records.
- Checkpoints are persisted after every step, allowing interrupted runs to resume without repeating completed side effects.

### 6. Independent Verification
- Execution success is determined **exclusively** by independent deterministic checks, never by model self-evaluation.
- Mandatory checks include: `plan_exists`, `repository_context`, `tool_allowlist`, and external command verification (`git.diff.check`, `python.tests`).

### 7. Failure Diagnosis & Bounded Reflection
- If any step or verification check fails, errors are classified into categories:
  - `POLICY_VIOLATION` (fatal, non-recoverable)
  - `TIMEOUT` (recoverable with scoped arguments)
  - `SYNTAX_ERROR` (recoverable with patch fix)
  - `DEPENDENCY_MISSING` (fatal, admits missing environment dependencies)
  - `VALIDATION_FAILURE` (recoverable within retry budget)
- If recoverable and `retry_count < max_retries`, the agent retries bounded actions.
- If exhausted or fatal, transitions cleanly to `FAILED` with an evidence-based diagnosis.

### 8. Evidence Report
- Returns the complete run checkpoint, tool execution logs, independent check results, and execution timeline.
