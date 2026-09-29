# Agentic Software Engineer

> **An auditable AI software-engineering agent that can inspect a repository, plan bounded changes, execute guarded actions, verify its work, and expose the evidence to an operator.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Web-Next.js-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![Safety](https://img.shields.io/badge/execution-guarded-success)](#safety-model)
[![License](https://img.shields.io/badge/license-MIT-blue)](#license)

## Why this project?

Most agent demos stop at **"LLM generates code."**

This project treats software engineering as a controlled system:

**Observe → Understand → Plan → Policy Check → Execute → Verify → Reflect**

The model is advisory. The execution boundary is deterministic, typed, bounded, and independently verifiable.

## What it can do

| Layer | Capability |
|---|---|
| **Observe** | Bounded repository traversal, language/file inventory |
| **Understand** | Repository-aware task context and deterministic planning |
| **Plan** | Typed plan steps and tool contracts |
| **Policy** | Fail-closed tool allowlist and bounded workspace actions |
| **Execute** | Dry-run workspace mutations and structured commands |
| **Verify** | Independent artifact checks + command evidence |
| **Reflect** | Failure diagnosis and bounded retry contract |
| **Analyze** | Diff/change-risk classification |
| **AI** | Provider abstraction + optional local Ollama advisory |
| **GitHub** | Branch/PR/merge safety contracts |
| **Operate** | Live dashboard with run status, evidence and timeline |

## Architecture

```text
                    ┌──────────────────────────┐
                    │       Operator UI        │
                    │     Next.js dashboard    │
                    └────────────┬─────────────┘
                                 │
                                 ▼
                    ┌──────────────────────────┐
                    │       FastAPI API         │
                    │   Run / Diff / Advisory   │
                    └────────────┬─────────────┘
                                 │
              ┌──────────────────┴──────────────────┐
              ▼                                     ▼
     ┌────────────────┐                    ┌────────────────┐
     │   Repository   │                    │  Plan + Policy │
     │  Intelligence  │──────────────────▶│    Engine      │
     └────────────────┘                    └───────┬────────┘
                                                   │
                         ┌─────────────────────────┼────────────────────────┐
                         ▼                         ▼                        ▼
                ┌────────────────┐       ┌────────────────┐       ┌────────────────┐
                │ Workspace      │       │ Command Runner │       │ GitHub Workflow│
                │ Executor       │       │  Allowlisted   │       │    Contracts   │
                └───────┬────────┘       └───────┬────────┘       └────────────────┘
                        └────────────────────────┼────────────────────────┘
                                                 ▼
                                      ┌────────────────────┐
                                      │ Independent        │
                                      │ Verification       │
                                      └─────────┬──────────┘
                                                ▼
                                      ┌────────────────────┐
                                      │ Evidence + Reflect │
                                      └────────────────────┘
```

## Safety model

The most important design choice is **not giving the planner an unrestricted shell**.

### Command boundary

Commands are stable IDs rather than arbitrary shell strings:

- `python.tests`
- `python.compile`
- `git.diff.check`

Execution uses:

- `shell=False`
- repository-root working directory
- sanitized environment
- 60-second hard timeout cap
- 32 KiB stdout/stderr cap
- explicit non-zero exit handling

### Workspace boundary

- Mutations are dry-run by default.
- Paths are resolved and checked against the configured workspace root.
- Action types are explicitly allowlisted.
- Action counts are bounded.

### Verification boundary

Planning does not determine whether a run succeeded.

Verification independently produces structured evidence. A run only completes when required verification gates pass.

> **Important:** this is application-level execution safety, not an OS-level sandbox. Untrusted repositories should be isolated in disposable containers/VMs with resource quotas and restricted networking before real mutation is enabled.

## AI strategy

The project deliberately introduces AI **after** the deterministic safety layer.

Current architecture:

```text
Local Ollama / future provider
          │
          ▼
   PlanningProvider
          │
          ▼
 deterministic control loop
          │
          ├── policy
          ├── execution
          └── verification
```

If Ollama is unavailable or unconfigured, the system falls back to a deterministic provider.

That makes the core runnable without paid model APIs.

## API

### Health

`GET /api/health`

### Run an engineering task

`POST /api/v1/runs`

```json
{
  "task": {
    "title": "Review repository change",
    "description": "Inspect the repository and verify the proposed work.",
    "repository": "/workspace/repo"
  }
}
```

### Analyze a diff

`POST /api/v1/analyze-diff`

Returns additions, deletions, per-file risk and aggregate risk.

### Advisory planning

`POST /api/v1/advisory`

Uses Ollama when configured and deterministic planning otherwise.

## Project structure

```text
agentic_software_engineer/
├── apps/
│   ├── api/
│   │   ├── app/
│   │   │   ├── repository.py
│   │   │   ├── planner.py
│   │   │   ├── policy.py
│   │   │   ├── execution.py
│   │   │   ├── command_runner.py
│   │   │   ├── verification_pipeline.py
│   │   │   ├── change_analysis.py
│   │   │   ├── reflection.py
│   │   │   ├── providers.py
│   │   │   ├── llm.py
│   │   │   └── workflow.py
│   │   └── tests/
│   └── web/
├── docs/
│   └── architecture/
├── docker-compose.yml
└── .github/workflows/
```

## Run locally

### API

```bash
cd apps/api
python -m venv .venv
# activate .venv
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://localhost:8000` if needed.

### Docker

```bash
docker compose up --build
```

The local stack exposes the web UI on port 3000 and the API on port 8000.

## Testing

API tests:

```bash
cd apps/api
pytest -q
ruff check .
```

The repository also contains GitHub Actions CI for API tests/linting and the web build.

## Portfolio talking points

If presenting this project in an interview, focus on these engineering decisions:

1. **Why deterministic first?**  
   Safety, reproducibility and debuggability are easier to establish before introducing probabilistic planning.

2. **Why not arbitrary shell execution?**  
   An agent that can execute arbitrary strings is an uncontrolled automation surface. Stable command IDs make the boundary inspectable and enforceable.

3. **Why independent verification?**  
   The component that proposes work should not be the sole authority that declares the work successful.

4. **Why local-model support?**  
   It keeps experimentation free and private while preserving a provider abstraction for future hosted models.

5. **What would you do next?**  
   Container-level isolation, resource quotas, dependency/symbol graphs, semantic repository retrieval, persistent run storage, and real GitHub issue/branch/PR execution behind explicit operator approval.

## Project status

**Portfolio-ready engineering prototype.**

Implemented through the guarded execution, verification, agentic-core and production-hardening phases. CI configuration is committed, but a GitHub Actions run is not currently exposed through the connected GitHub integration, so this README intentionally does not claim a verified green build.

## License

MIT.
