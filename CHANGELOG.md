# Changelog

## 0.8.0 — Autonomous Execution Hardening & Verification V2
- **Typed, Dependency-Aware Execution DAGs**: Enhanced `PlanStep` with explicit prerequisites (`depends_on`), preconditions, postconditions, and attempt tracking.
- **Cryptographic Approval Binding**: Approvals bound to deterministic SHA-256 fingerprints of plan definitions and unified diffs; automatic invalidation (`APPROVAL_INVALIDATED`) upon plan or workspace divergence.
- **Disciplined Self-Correction Loop**: Implemented `SelfCorrectionEngine` with anti-cycling loop prevention (`STRATEGY_LOOP`), multi-category failure diagnosis, and AST Security Critic diff gating.
- **Cancellation & Abort Propagation**: Added cancellation support across `AgentRun`, REST API (`POST /api/v1/runs/{run_id}/cancel`), WebSocket bidirectional streams, and CLI `cancel`.
- **Machine-Readable Step-Linked Verification**: Upgraded verification pipeline with explicit `step_id`, `category`, `expected`, `actual`, and ISO-8601 timestamps.
- **Evaluation Benchmark Expansion**: Expanded evaluation suite from 15 to 20 comprehensive scenarios with 100% pass rate, 100% policy adherence, and 100% truthfulness.
- **Web Dashboard Hardening**: Added Run Cancellation, cryptographic approval fingerprints, explicit Reject action, and step precondition/postcondition indicators in Next.js UI.

## 0.7.0 — Resilient Execution & Reflection
- Added SQLite Operation Journal with WAL mode for crash-safe execution recovery.
- Added deterministic idempotency keys and pre/post-condition hashing to prevent duplicate side effects.
- Added AST-based Security Critic for secret detection, dynamic execution review, and SQL injection blocking.
- Added Deliberation Council multi-agent consensus workflow (Architect, Coder, Critic).
- Added SWE-bench style benchmark runner and CodeGraph symbol indexer.

## 0.6.0 — Production Hardening
- Added optional Ollama local-model advisory planning.
- Added deterministic fallback when local AI is not configured or unavailable.
- Added CORS configuration and baseline security headers.
- Added API and web container definitions plus Docker Compose.
- Added environment configuration template.

## 0.5.0 — Agentic Core
- Added deterministic diff/change-risk analysis.
- Added bounded reflection and retry-budget contracts.
- Added provider abstraction with deterministic fallback.
- Added GitHub workflow policy contracts requiring green verification before merge.
- Added operator dashboard with live run submission and verification evidence.

## 0.4.0 — Command Verification Boundary
- Added structured allowlisted command execution.
- Added shell=False, timeout and output-size boundaries.
- Added sanitized execution environment.
- Added independent verification evidence and command evidence.

## 0.3.0 — Guarded Execution
- Added bounded workspace execution primitives.
- Added dry-run-by-default mutation semantics.
- Added path traversal protection and action policy.

## 0.2.1 — Context-Aware Planning
- Wired repository inspection into the agent planning loop.
- Added repository-context verification.

## 0.2.0 — Repository Intelligence
- Added bounded local repository inspection.

## 0.1.0 — Foundation
- Initialized the control plane.
