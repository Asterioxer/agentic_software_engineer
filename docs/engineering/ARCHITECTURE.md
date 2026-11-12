# System Architecture & Technical Specifications

**Autonomous Control Lifecycle:**
$$\text{TaskSpec} \longrightarrow \text{CodeGraph} \longrightarrow \text{Planner (DAG)} \longrightarrow \text{Cryptographic Approval} \longrightarrow \text{WAL Journal} \longrightarrow \text{Guarded Exec} \longrightarrow \text{Verification} \longrightarrow \text{Self-Correction}$$

---

## 1. Subsystems

### A. Repository Intelligence (`apps/api/app/codegraph.py`, `code_context.py`)
- Source file discovery with ignore list (`.git`, `node_modules`, `venv`, `__pycache__`).
- Symbol definition extraction (AST classes, functions, async functions, TypeScript interfaces).
- Import resolution (external and intra-package relative imports).
- Dependency graph with bidirectional edges (`file_dependencies`, `file_dependents`).
- Transitive blast radius computation with affected test file discovery.
- Cycle detection across modular import graphs.

### B. Structured Planning (`apps/api/app/planner.py`)
- Typed `PlanStep` sequence with inputs, outputs, validation criteria, and DAG dependencies (`depends_on`).
- Explicit preconditions and postconditions.
- Mutation steps marked with `requires_approval = True`.

### C. Cryptographic Approval Gate (`apps/api/app/runner.py`)
- Fingerprint: $\text{SHA-256}(\text{Canonical Plan} \parallel \text{Unified Diff})$.
- Pre-state hash: $\text{SHA-256}(\text{Target Files Content})$ at time of approval request.
- Strict TOCTOU validation upon `resume_run`: disk state divergence triggers immediate `APPROVAL_INVALIDATED`.
- Time-To-Live expiration timestamp (`expires_at`).

### D. Durable Execution & Operation Journaling (`apps/api/app/store.py`)
- SQLite database in Write-Ahead Logging (`WAL`) mode with `busy_timeout=5000`.
- Operation journal tracking each tool step (`operation_id`, `idempotency_key`, `input_hash`, `precondition_hash`, `postcondition_hash`, `state`).
- Reconciles interrupted operations upon runner boot without repeating completed work (idempotent replay).

### E. Guarded Tool Execution (`apps/api/app/execution.py`, `patch.py`, `command_runner.py`)
- `WorkspaceExecutor`: atomic writes and deletes with path containment, symlink escape rejection, UNC and NTFS stream defenses.
- `PatchApplier`: unified diff parser with transactional rollback, pre/post-condition hashing, and strict VCS/`.env` protection.
- `CommandRunner`: allowlisted structured command execution with `shell=False`, timeout cap (60s), output limit (32 KiB), and recursive process tree termination.

### F. Multi-Stage Independent Verification (`apps/api/app/verification.py`)
- AST syntax checking across Python, JSON, and TOML.
- Proof of test validation (requires non-empty test definitions with real assertions).
- AST Security Critic scanning for credential secrets, dynamic execution (`eval`, `exec`), shell calls, and SQL injections.
- Workspace boundary containment checks.

### G. Self-Correction & Anti-Cycling Engine (`apps/api/app/self_correction.py`)
- Multi-category failure classification.
- Failure signature fingerprinting ($\text{category} \parallel \text{error message} \parallel \text{target file}$).
- Anti-cycling detection halts identical repair repeats with `STRATEGY_LOOP`.
- Proposed code gated by AST Security Critic.
