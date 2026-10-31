# Agentic Software Engineer

> **A reliable, auditable autonomous software-engineering agent that inspects repositories, plans bounded changes, executes guarded actions, verifies work independently, and exposes complete evidence to an operator.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Web-Next.js-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Tests](https://img.shields.io/badge/Tests-41%20passing-brightgreen)](https://github.com/Asterioxer/agentic_software_engineer)
[![Coverage](https://img.shields.io/badge/Coverage-88%25-success)](https://github.com/Asterioxer/agentic_software_engineer)
[![Safety](https://img.shields.io/badge/execution-guarded-success)](#safety-model)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

---

## Why this project?

Most agent demos stop at **"LLM generates code and blindly runs shell commands."**

This project treats software engineering as a **controlled, observable, verifiable system**:

**User Request → Repository Understanding → Task Decomposition → Execution Plan → Operator Approval → Tool Execution → Independent Verification → Failure Diagnosis → Final Report**

The LLM is strictly advisory. The execution boundary is **deterministic, typed, fail-closed, bounded, and independently verified**.

---

## Key Capabilities

| Layer | Capability |
|---|---|
| **Repository Intelligence** | Bounded traversal (500 files), language inventory, symbol extraction (Python & TypeScript), and prompt-injection defanging. |
| **Structured Planning** | Inspectable, typed `PlanStep` sequence with explicit inputs, expected outputs, and validation criteria. |
| **Operator Approval Gate** | Non-dry-run mutating operations automatically halt at `AWAITING_APPROVAL` until explicit operator sign-off. |
| **Persistent Execution Store** | SQLite-backed run checkpoints, timeline events, and tool audit records with safe task resumption. |
| **Bounded Execution** | Strict path containment (symlink defense), tool allowlisting, shell-free command execution (`shell=False`), 60s hard timeout cap, and 32 KiB stream limit. |
| **Independent Verification** | External deterministic checks (file presence, `git diff --check`, test exit codes); the agent **never** decides its own success. |
| **Failure Classification & Reflection** | Automatic error categorization (`POLICY_VIOLATION`, `TIMEOUT`, `SYNTAX_ERROR`, `DEPENDENCY_MISSING`, `VALIDATION_FAILURE`) with bounded retry budgets. |
| **Evaluation Harness** | 10 automated benchmark scenarios grading task completion, policy adherence, truthfulness, and anti-hallucination. |
| **Operator Dashboard** | Full Next.js control center for execution tracking, step inspections, approval controls, diff risk analysis, and evaluation benchmarks. |

---

## Architecture

```text
                     ┌─────────────────────────────────────────┐
                     │          Next.js Operator UI            │
                     │  Control / Diff / Approval / Evaluation │
                     └────────────────────┬────────────────────┘
                                          │
                                          ▼
                     ┌─────────────────────────────────────────┐
                     │            FastAPI Backend              │
                     │   Runs / Checkpoints / Diff / Advisory  │
                     └────────────────────┬────────────────────┘
                                          │
               ┌──────────────────────────┴──────────────────────────┐
               ▼                                                     ▼
      ┌────────────────┐                                    ┌────────────────┐
      │   Repository   │                                    │ Persistent Run │
      │  Intelligence  │                                    │  SQLite Store  │
      │  & Defanged    │                                    └───────┬────────┘
      │  Code Context  │                                            │
      └────────┬───────┘                                            │
               │                                                    │
               ▼                                                    ▼
      ┌────────────────┐      Operator Approval Gate       ┌────────────────┐
      │ Structured     │──────────────────────────────────▶│ Guarded Tool   │
      │ Planning Engine│    (Awaiting Approval if Mutating)│ Execution Loop │
      └────────────────┘                                   └───────┬────────┘
                                                                   │
                                  ┌────────────────────────────────┴────────────────┐
                                  ▼                                                 ▼
                         ┌────────────────┐                                ┌────────────────┐
                         │ Workspace Path │                                │ Shell-Free     │
                         │ Boundary       │                                │ Command Runner │
                         │ (Dry-Run Def.) │                                │ (Allowlisted)  │
                         └───────┬────────┘                                └───────┬────────┘
                                 └────────────────────────┬────────────────────────┘
                                                          ▼
                                               ┌────────────────────┐
                                               │ Independent        │
                                               │ Verification Gates │
                                               └─────────┬──────────┘
                                                         ▼
                                               ┌────────────────────┐
                                               │ Failure Diagnosis  │
                                               │ & Bounded Retries  │
                                               └────────────────────┘
```

---

## Safety Model

### 1. Command Execution Boundary
Commands are stable, allowlisted IDs executed with `subprocess.run(shell=False)`:
- `python.tests`: `python -m pytest`
- `python.compile`: `python -m compileall`
- `python.ruff`: `python -m ruff check`
- `git.diff.check`: `git diff --check`
- `git.status`: `git status --short`
- `git.diff`: `git diff`

No arbitrary shell interpolation is permitted. Timeouts are capped at 60s and output streams are capped at 32 KiB.

### 2. Workspace & Filesystem Boundary
- Workspace actions default to `dry_run=True`.
- Strict path normalization rejects null bytes (`\0`) and escapes from the configured repository root (`../`).
- Direct modification of `.git` internals or `.env` files is blocked.

### 3. Application Controls vs. OS Sandboxing
> **Important Distinction:** The security controls provided here are application-level guardrails, not OS-level container isolation. Host-level isolation (e.g. Docker, firecracker microVMs) must be provisioned when running against untrusted repositories.

---

## Evaluation Benchmark Suite

An automated, independent evaluation harness benchmarks the agent across 10 distinct failure and safety scenarios:

1. **Successful Coding**: Valid task execution and verification pass.
2. **Ambiguous Task**: Graceful discovery planning without hallucinating changes.
3. **Missing Dependencies**: Identifies missing environment dependencies and halts cleanly.
4. **Invalid Tool Arguments**: Strict Pydantic schemas reject malformed arguments.
5. **Tool Timeout**: Enforces timeout limits and reports failure evidence.
6. **API Failures**: Seamless fallback from remote LLM to deterministic provider.
7. **Prompt Injection**: Defangs adversarial instructions embedded in repo files.
8. **Policy Bypass**: Fail-closed defense rejecting unauthorized tool calls.
9. **Regression Detection**: Catches broken verification checks without false positives.
10. **Honest Failure**: Refuses to claim success when impossible verification criteria fail.

### Running the Evaluation Suite

```bash
cd apps/api
pytest tests/test_evaluation_harness.py -v
```

Machine-readable evaluation reports are generated at `evaluation_reports/evaluation_report.json`.

---

## API Reference

### Health
`GET /api/health`

### Dispatch a Task Run
`POST /api/v1/runs`
```json
{
  "task": {
    "title": "Add logging module",
    "description": "Implement structured audit logging in src/logger.py",
    "repository": "C:/path/to/repo",
    "dry_run": true,
    "auto_approve": false,
    "max_retries": 2
  }
}
```

### List Runs
`GET /api/v1/runs`

### Inspect Run Checkpoint & Evidence
`GET /api/v1/runs/{run_id}`

### Approve & Resume a Paused Run
`POST /api/v1/runs/{run_id}/resume`
```json
{
  "approved": true
}
```

### Analyze Unified Diff Risk
`POST /api/v1/analyze-diff`
```json
{
  "diff": "diff --git a/app/auth.py b/app/auth.py\n..."
}
```

### Run Evaluation Suite
`POST /api/v1/evaluations/run`

---

## Local Setup & Quickstart

### Prerequisites
- Python 3.12+
- Node.js 20+

### 1. API Setup
```bash
cd apps/api
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### 2. Web Dashboard Setup
```bash
cd apps/web
npm install
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) to open the operator dashboard.

### 3. Docker Compose
```bash
docker compose up --build
```

---

## Verification & Testing

Run the complete test suite (41 tests, unit, integration, safety boundary, API, and E2E):
```bash
cd apps/api
pytest -v
```

Run test coverage report (88% code coverage):
```bash
cd apps/api
pytest --cov=app --cov-report=term-missing
```

Code quality and strict type checks:
```bash
cd apps/api
ruff check .
ruff format --check .
mypy app
```

Frontend production build check:
```bash
cd apps/web
npm run build
```

---

## License

MIT.
