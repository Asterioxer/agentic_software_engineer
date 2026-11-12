# AGENTIC SOFTWARE ENGINEER ∞
# MASTER ROADMAP

**System Directive:** Continuously evolve the autonomous software engineering system without artificial stopping points, prioritizing correctness, execution integrity, security, recoverability, independent verification, and truthfulness.

---

## Strategic Pillars & Capability Horizons

### Pillar 1: Autonomous Repository Intelligence
- [x] Bounded file system traversal and language classification.
- [x] Symbol extraction for Python AST and TypeScript/JavaScript.
- [x] Dependency edge and blast radius computation.
- [x] Prompt-injection defanging in context snippets.
- [ ] **Next:** Resolved relative Python package imports (`node.level`).
- [ ] **Next:** Cycle detection in dependency graphs (`detect_cycles`).
- [ ] **Next:** Orphan file discovery (`find_orphan_files`).
- [ ] **Next:** Cross-file call-graph and caller/callee tracing.

### Pillar 2: Cryptographic Authorization & TOCTOU Integrity
- [x] Deterministic plan serialization and SHA-256 fingerprinting.
- [x] Unified diff binding to approval requests.
- [x] Explicit operator rejection (`approved=False`).
- [ ] **Next:** Time-of-Check to Time-of-Use (TOCTOU) workspace state hashing (`workspace_pre_state_hash`).
- [ ] **Next:** Approval TTL and automatic expiration (`expires_at`).
- [ ] **Next:** Disk divergence detection halting unverified mutation resumption.

### Pillar 3: Adversarial Security Engineering & Patch Containment
- [x] `shell=False` execution with strict command allowlisting.
- [x] Path traversal rejection (`..`, null bytes, drive letters, UNC, alternate data streams in `WorkspaceExecutor`).
- [x] Sensitive file protection (`.git`, `.env` in `WorkspaceExecutor`).
- [ ] **Next:** Strict path validation in `PatchApplier` (null bytes, UNC, drive letters, `.git`, `.env`).
- [ ] **Next:** Symlink and junction escape defense in `PatchApplier` and `WorkspaceExecutor`.
- [ ] **Next:** Refusal to write through or follow symlinks.

### Pillar 4: Durable Control Plane & Self-Correction
- [x] SQLite Operation Journal with WAL mode.
- [x] Crash reconciliation from postcondition hashes.
- [x] Idempotent operation deduplication.
- [x] Multi-category failure classification.
- [x] Anti-cycling loop prevention (`STRATEGY_LOOP`).
- [x] AST Security Critic diff gating before repair application.
- [ ] **Next:** Stress and crash-injection test harness across DAG step transitions.
- [ ] **Next:** Fine-grained timeout and process-tree cancellation verification.

### Pillar 5: Comprehensive Benchmark & Evaluation Harness
- [x] Scenarios 1–15: Baseline failure, crash recovery, replay, oversized output, prompt injection.
- [x] Scenarios 16–20: Approval invalidation, cancellation, anti-cycling, false-positive verification, concurrency lock.
- [ ] **Next:** Scenario 21: TOCTOU workspace pre-state divergence.
- [ ] **Next:** Scenario 22: Approval TTL expiration.
- [ ] **Next:** Scenario 23: Symlink traversal patch rejection.
- [ ] **Next:** Scenario 24: VCS/`.git` patch injection defense.
- [ ] **Next:** Scenario 25: Circular dependency detection.
