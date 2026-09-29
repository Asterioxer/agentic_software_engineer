# Agentic Software Engineer

A guarded, auditable control plane for repository-aware software-engineering agents.

## Control loop

Observe → Understand → Plan → Policy Check → Execute → Verify → Reflect

## Current capabilities

- Bounded repository inspection with language/file summaries.
- Deterministic, repository-aware planning.
- Dry-run-by-default workspace mutations with root traversal protection.
- Explicit tool policy and typed tool calls.
- Structured command execution with an allowlist; no arbitrary shell strings.
- Hard command timeout and bounded stdout/stderr capture.
- Independent verification evidence and failure propagation.
- FastAPI control-plane endpoint at POST /api/v1/runs.
- CI-oriented Python project structure with pytest, Ruff and mypy configuration.

## Safety model

The project intentionally does not claim OS-level sandboxing. Command execution is bounded at the application layer. A production deployment that executes untrusted repositories should additionally isolate each run in a disposable container or VM with resource quotas and a restricted network.

## Roadmap

1. Repository intelligence
2. Guarded workspace execution
3. Sandboxed command/verification boundary
4. Diff and patch intelligence
5. Provider-agnostic LLM planning with deterministic fallback
6. GitHub issue/branch/PR automation
7. Failed-verification diagnosis and bounded self-correction
8. Evidence timeline and operator dashboard
9. Production deployment
