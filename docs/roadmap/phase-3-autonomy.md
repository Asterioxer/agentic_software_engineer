# Phase 3 Strategic Architecture & Evolution Roadmap
## Transitioning from Guarded Assistant to Autonomous Engineering Fleet

---

## 1. Executive Summary

Phase 2 established a deterministic, auditable, crash-resilient autonomous software engineering agent equipped with:
- ACID-compliant SQLite execution state and operation journaling.
- Strict tool allowlists and argument schemas.
- SHA-256 precondition/postcondition atomic mutation and reconciliation.
- Multi-file unified diff engine (`workspace.patch`).
- Automated AST and heuristic Security Critic (`app.critic`).
- Ephemeral Git Worktree isolation (`app.worktree`).
- 15-scenario independent verification benchmark with 100% pass rate.

**Phase 3 shifts the system from single-task local execution to an autonomous, distributed, enterprise-ready software engineering platform.** This document specifies the architectural blueprints, technical milestones, and design contracts required for Phase 3.

---

## 2. Milestone Overview

| Milestone | Title | Focus Area | Complexity |
|---|---|---|---|
| **M1** | MicroVM & Container Sandboxing | True OS-level execution isolation | High |
| **M2** | Deliberation Topology (Council of Agents) | Multi-agent specialization & consensus | Medium |
| **M3** | Real-Time SSE Dashboard Telemetry | Streaming token & execution visibility | Medium |
| **M4** | SWE-bench Automated Benchmark Harness | Industry-standard realistic coding eval | High |
| **M5** | Distributed Task Orchestration | Fault-tolerant queue & multi-repo workers | High |

---

## 3. Milestone Specifications

### 3.1 Milestone 1: MicroVM & Container Sandboxing (OS-Level Isolation)

#### Context & Problem
Currently, tool execution safety relies on application-level controls: command tokenization, path canonicalization, and allowlisting. However, running arbitrary test suites (`pytest`, `npm test`, arbitrary code execution) on the host machine inherently carries risks of kernel exploits, resource exhaustion (fork bombs), and unauthorized network egress.

#### Target Architecture
```
Host Controller (FastAPI Agent)
        │
        ├── Ephemeral Worktree (Local Git FS)
        │       │
        │  Mount (Read-Write Task Slice)
        ▼       ▼
┌────────────────────────────────────────┐
│  gVisor (runsc) / Firecracker MicroVM  │
│  - No host root access                 │
│  - Isolated network namespace (mocked) │
│  - Resource caps: 2 vCPU, 2GB RAM      │
│  - Read-only rootfs                    │
│  - Ephemeral tmpfs (/tmp)              │
└────────────────────────────────────────┘
```

#### Key Implementation Steps:
1. **Container Backend Interface (`app/sandbox/base.py`):**
   - Abstract base class `ExecutionSandbox` defining `exec_command(cmd, timeout, env, cwd) -> CommandResult`.
2. **Docker / Podman / gVisor Implementation (`app/sandbox/container.py`):**
   - Configures ephemeral containers mounted with only the target worktree.
   - Disables inter-container communication and host network access (`--network none` by default, or `--network internal` with proxy allowlisting).
   - Enforces cgroups v2 resource quotas: `memory=2G`, `cpu_quota=200000`.
3. **Transparent Runner Hook:**
   - Modify `CommandRunner` in `app/command_runner.py` to route commands through `ExecutionSandbox` when enabled, with zero changes to planner contracts.

---

### 3.2 Milestone 2: Deliberation Topology (Council of Specialized Agents)

#### Context & Problem
A single monolithic prompt attempting to analyze requirements, write patches, review security, and verify tests suffers from attention dilution, sycophancy, and self-serving bias (validating its own flawed assumptions).

#### Target Architecture
```
                  ┌─────────────────┐
                  │  Operator Task  │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │    ARCHITECT    │ (Repository Indexing, Decomposition,
                  └────────┬────────┘  Plan Step Generation)
                           │
                           ▼
                  ┌─────────────────┐
                  │      CODER      │ (Generates Unified Diffs,
                  └────────┬────────┘  Fixes, Unit Tests)
                           │
            ┌──────────────┴──────────────┐
            ▼                             ▼
   ┌─────────────────┐           ┌─────────────────┐
   │ SECURITY CRITIC │           │    VERIFIER     │
   │ (AST & Pattern  │           │ (Builds, Tests, │
   │  Vulnerabilities│           │  Coverage Regr.)│
   └────────┬────────┘           └────────┬────────┘
            └──────────────┬──────────────┘
                           │ Consensus Gated
                           ▼
                  ┌─────────────────┐
                  │    OPERATOR     │ (Approval / Commit)
                  └─────────────────┘
```

#### Key Implementation Steps:
1. **Agent Role Specialization:**
   - **Architect Agent:** High-level context reasoning, dependency mapping, generation of discrete, typed `PlanStep` sequences.
   - **Coder Agent:** Implementation of hunks targeting specific files; strictly barred from evaluating test outputs.
   - **Critic Agent:** Deterministic static analysis + LLM-based architectural sanity check. Barred from writing code.
   - **Verifier Agent:** Runs sandbox tests, gathers coverage deltas, checks for behavioral regressions.
2. **Structured Deliberation Consensus (`app/deliberation/`):**
   - Two-phase commit: Before any mutation is applied, Coder and Critic must reach signed agreement.
   - Disagreement triggers an automated reflection round (max 2 iterations) before human escalation.

---

### 3.3 Milestone 3: Real-Time SSE Telemetry & Dashboard Streaming

#### Context & Problem
Currently, the operator dashboard polls the backend via REST endpoints (`/api/v1/runs/{run_id}`). While robust and simple, polling introduces latency (1–2 seconds) and does not convey progressive streaming thoughts, tool logs, or real-time subprocess stdout/stderr.

#### Target Architecture
```
Backend (FastAPI) ──────────────── SSE Stream ───────────────► Frontend (Next.js)
  EventBus:                                                    EventSource:
  - run:started                                                - Live execution log
  - step:progress (stdout chunks)                              - Real-time terminal
  - tool:executing (args, preview)                             - Interactive diff viewer
  - critic:finding                                             - Instant approval modal
  - run:completed / paused
```

#### Key Implementation Steps:
1. **In-Memory & Persisted Event Bus (`app/telemetry/events.py`):**
   - FastAPI `EventSourceResponse` endpoint `GET /api/v1/runs/{run_id}/stream`.
   - Streaming channel yielding typed events: `RunEvent(type="tool_output", payload={"chunk": "..."})`.
2. **Next.js Hook (`apps/web/hooks/use-run-stream.ts`):**
   - React 19 hook maintaining active `EventSource` connection with automatic reconnection and replay buffer.
3. **Interactive Terminal Component (`apps/web/components/terminal-stream.tsx`):**
   - Virtualized terminal output rendering streaming subprocess stdout/stderr in real time without browser lag.

---

### 3.4 Milestone 4: SWE-bench Automated Benchmark Harness

#### Context & Problem
The current 15-scenario benchmark rigorously tests unit failure modes, prompt injection, and recovery. However, evaluating true software engineering prowess requires testing against real-world GitHub issues and full codebases.

#### Target Architecture
```
SWE-bench Lite Dataset (300 Real GitHub Python Issues)
        │
        ├── Problem Statement + Golden Test Suite
        ▼
Autonomous Coding System
        │
        ├── Context Retrieval (Codebase search)
        ├── Unified Patch Generation (`workspace.patch`)
        ├── Security Critic Gate
        └── Test Execution (MicroVM Sandbox)
        ▼
Independent Evaluator
        ├── Checks PASS_TO_PASS and FAIL_TO_PASS
        └── Computes Resolve Rate (%)
```

#### Key Implementation Steps:
1. **SWE-bench Connector (`app/evaluation/swe_bench.py`):**
   - Harness that ingests standard SWE-bench JSON / HuggingFace datasets.
   - Automatically checks out target repo commit and mounts it in an ephemeral worktree.
2. **Strict Evaluation Metrics:**
   - Resolved Rate (% of issues where all fail-to-pass tests pass and pass-to-pass tests do not regress).
   - Cost & Token Efficiency (Tokens / Resolved Issue).
   - Wall-Clock Completion Time.

---

### 3.5 Milestone 5: Distributed Task Orchestration & Multi-Repo Fleets

#### Context & Problem
For enterprise deployment, tasks must execute across multiple repositories concurrently with centralized durability, rate-limiting, and worker pools.

#### Target Architecture
```
                 ┌───────────────────────────┐
                 │  API Gateway & Scheduler  │
                 └─────────────┬─────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
       ┌─────────────────┐           ┌─────────────────┐
       │  Temporal / SQS │           │  Temporal / SQS │
       │  Repo A Queue   │           │  Repo B Queue   │
       └────────┬────────┘           └────────┬────────┘
                ▼                             ▼
       ┌─────────────────┐           ┌─────────────────┐
       │ Worker Pool #1  │           │ Worker Pool #2  │
       │ (Agent Runner)  │           │ (Agent Runner)  │
       └─────────────────┘           └─────────────────┘
```

#### Key Implementation Steps:
1. **Temporal Workflow Integration:**
   - Model the agent execution loop (`TaskDecomposition -> Approval -> Execution -> Verification`) as a durable, deterministic Temporal workflow.
   - Survives full host machine restarts and worker crashes without data loss.
2. **Centralized PostgreSQL Store:**
   - Expand `RunStore` SQLite backend to support PostgreSQL with row-level locking (`FOR UPDATE SKIP LOCKED`) for high-concurrency worker fleets.

---

## 4. Phase 3 Implementation Timeline & Phases

```
┌────────────────────────────────────────────────────────┐
│ Q1: Milestone 1 (Container Sandboxing) + SSE Streaming │
├────────────────────────────────────────────────────────┤
│ Q2: Milestone 2 (Council of Agents Deliberation)       │
├────────────────────────────────────────────────────────┤
│ Q3: Milestone 4 (SWE-bench Automated Evaluation)       │
├────────────────────────────────────────────────────────┤
│ Q4: Milestone 5 (Distributed Fleets & Temporal)        │
└────────────────────────────────────────────────────────┘
```

---

## 5. Architectural Non-Negotiables
1. **Deterministic Verification Remains Sovereign:** No agent can mark its own task successful. Independent test runners and static critics retain absolute veto authority.
2. **Zero Ambient Authority:** Every tool call and mutation must be scoped to an ephemeral worktree with pre- and post-condition hash verification.
3. **Audit Trails for Everything:** Every LLM prompt, response, tool invocation, and critic finding must be permanently journaled in durable storage.
