# Phase 4 Strategic Architecture & Enterprise Evolution Roadmap
## Autonomous Engineering at Fleet Scale: Multi-Worker, CI Bot, and Model Distillation

---

## 1. Executive Summary

Phase 2 and Phase 3 established a hardened, crash-resilient autonomous software engineering agent equipped with:
- ACID-compliant SQLite execution state and durable operation journaling.
- Multi-file atomic unified diff engine (`workspace.patch`) with SHA-256 pre/postcondition hashes.
- AST and heuristic Security Critic (`app.critic`).
- Ephemeral Git Worktree isolation (`app.worktree`).
- Pluggable execution sandboxes (guarded local subprocess & containerized `DockerSandbox`).
- Real-time duplex WebSocket & SSE telemetry with interactive operator controls.
- Specialized Multi-Agent Deliberation Council (Architect -> Coder -> Critic -> Verifier).
- Standardized SWE-bench autonomous evaluation harness.
- Advanced multi-provider LLM abstraction with token budgeting and automated code repair.

**Phase 4 scales this system to an enterprise-grade autonomous software engineering fleet capable of monitoring hundreds of repositories, responding to GitHub/GitLab webhooks, and self-improving through model distillation.**

---

## 2. Phase 4 Milestone Overview

| Milestone | Title | Focus Area | Target Impact |
|---|---|---|---|
| **M1** | Distributed Multi-Worker Orchestration | Temporal.io / Redis queue & worker pool | Concurrently run across 50+ repositories |
| **M2** | Autonomous GitHub & GitLab Bot | Webhook receiver, PR review & fix bot | Zero-human triage of automated issues |
| **M3** | SWE-bench Full Benchmark Automation | Ingestion of 2,294 SWE-bench instances | Industry-standard verification scoring |
| **M4** | Model Distillation & Fine-Tuning Pipeline | Dataset generator from verified journals | High-speed, local 7B/14B coding agents |
| **M5** | IDE & Chat Collaboration Integrations | VS Code extension & Slack/Discord bridge | Real-time human-in-the-loop steering |

---

## 3. Milestone Technical Specifications

### 3.1 Milestone 1: Distributed Multi-Worker Orchestration (Temporal / Celery)

#### Problem Statement
Currently, tasks execute inside the single FastAPI backend process. For high-volume enterprise workloads across multiple enterprise repositories, task dispatch, retry budgets, and worker heartbeats must be distributed across worker nodes.

#### Architectural Design
```
                     ┌───────────────────────────┐
                     │   FastAPI Control Plane   │
                     └─────────────┬─────────────┘
                                   │
                                   ▼
                     ┌───────────────────────────┐
                     │  Temporal / Redis Cluster │
                     │  - Durable Task Queues    │
                     │  - Worker Heartbeat Lease │
                     └─────────────┬─────────────┘
                                   │
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
┌──────────────────────┐┌──────────────────────┐┌──────────────────────┐
│  Worker Node 01      ││  Worker Node 02      ││  Worker Node 03      │
│  - Docker Sandbox    ││  - Docker Sandbox    ││  - Docker Sandbox    │
│  - Worktree Pool     ││  - Worktree Pool     ││  - Worktree Pool     │
│  - Telemetry Emitter ││  - Telemetry Emitter ││  - Telemetry Emitter │
└──────────────────────┘└──────────────────────┘└──────────────────────┘
```

#### Core Components to Implement:
1. **Temporal Workflow Definition (`app/workflows/task_workflow.py`):**
   - Workflow state machine modeling `TaskIntake -> ArchitectDecomposition -> PatchExecution -> CriticReview -> Verification`.
   - Activities run in ephemeral worker sandboxes with heartbeated execution leases.
2. **PostgreSQL Clustered Store (`app/store/postgres.py`):**
   - High-throughput database adapter replacing SQLite for distributed worker pools using row-level locks (`SELECT ... FOR UPDATE SKIP LOCKED`).

---

### 3.2 Milestone 2: Autonomous GitHub & GitLab Bot Integration

#### Problem Statement
Developers need the agent to triage bug reports, pull requests, and failing CI pipelines autonomously without requiring manual copy-pasting into a web dashboard.

#### Architectural Design
```
GitHub / GitLab Event
  (Issue Created, PR Failed, Comment Mention "@agentic-bot fix")
        │
        ▼
Webhook Gateway (`POST /api/v1/integrations/github/webhook`)
        │
        ├── Verify HMAC-SHA256 signature (`X-Hub-Signature-256`)
        ├── Parse issue description / failing CI log
        ├── Check branch permissions and allowlists
        ▼
Ephemeral Worktree Checkout
        │
        ├── Council Deliberation (Architect + Coder + Critic)
        ├── Containerized Verification (Pytest / Jest)
        └── Git Commit & Push to `bot/fix-<issue-number>`
        ▼
GitHub API Response
        └── Opens Pull Request with diff breakdown and verification evidence
```

---

### 3.3 Milestone 3: SWE-bench Full Automated Benchmark Automation

#### Problem Statement
While the current SWE-bench harness evaluates localized instances, executing the full 2,294 SWE-bench instances requires massive parallel container pooling, evaluation isolation, and standard leaderboard output formats.

#### Core Capabilities:
- Ingestion of SWE-bench Lite (300 instances) and SWE-bench Full (2,294 instances).
- Automated Docker image caching for Django, SymPy, Matplotlib, Astropy, Sphinx, and Scikit-learn environments.
- Comprehensive Pass@1, Resolve Rate (%), and Cost per Resolved Issue metrics.

---

### 3.4 Milestone 4: Model Distillation & Fine-Tuning Pipeline

#### Problem Statement
Frontier proprietary models (e.g. GPT-4o, Claude 3.5 Sonnet) are expensive for repetitive lint, syntax fix, and test repair loops. Small local models (Qwen2.5-Coder 7B/14B, DeepSeek-R1-Distill) can perform these tasks with lower latency and zero egress cost if fine-tuned on verified traces.

#### Pipeline Flow:
```
Durable Operation Journal (SQLite / Postgres)
  └── Filter for: State == SUCCEEDED and Verification == 100% PASS
        │
        ▼
Curated Training Pair Generator
  - Input: Prompt + Precondition File State + Test Error
  - Target: Surgical Unified Patch (`workspace.patch`) + Verification Proof
        │
        ▼
LoRA / QLoRA Fine-Tuning (Unsloth / Axolotl)
  └── Target: Qwen2.5-Coder-7B-Instruct / DeepSeek-Coder-14B
        │
        ▼
Quantization & Local Inference Deployment (vLLM / llama.cpp / Ollama)
```

---

### 3.5 Milestone 5: IDE & Chat Collaboration Integrations

1. **VS Code & JetBrains Extension:**
   - Sidebar extension connecting via WebSocket to `/api/v1/ws/runs/{run_id}`.
   - Inline diff inspection with one-click "Accept Patch" directly in editor gutter.
2. **Slack & Discord Bot Bridge:**
   - Real-time notification channel broadcasting run status.
   - Interactive buttons for approval gates: `[Approve Mutation]` / `[Reject]`.

---

## 4. Phase 4 Implementation Timeline

```
┌────────────────────────────────────────────────────────┐
│ Month 1: M1 (Temporal Orchestrator) + M2 (GitHub Bot)  │
├────────────────────────────────────────────────────────┤
│ Month 2: M3 (SWE-bench Full 300/2294 Parallel Eval)    │
├────────────────────────────────────────────────────────┤
│ Month 3: M4 (Model Distillation on Verified Journals)   │
├────────────────────────────────────────────────────────┤
│ Month 4: M5 (VS Code Extension & Slack Gateway)        │
└────────────────────────────────────────────────────────┘
```
