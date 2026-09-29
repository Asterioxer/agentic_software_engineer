# Agentic Software Engineer

A guarded, auditable control plane for repository-aware software-engineering agents.

## Control loop
Observe → Understand → Plan → Policy Check → Execute → Verify → Reflect

## Capabilities
- Bounded repository inspection and language summaries.
- Deterministic repository-aware planning.
- Dry-run-by-default workspace mutations with traversal protection.
- Structured allowlisted command execution with shell=False, timeout and output limits.
- Independent verification evidence and failure propagation.
- Deterministic diff/change-risk analysis.
- Bounded reflection and retry-budget contracts.
- Provider abstraction with a deterministic fallback.
- GitHub workflow policy requiring green verification before merge.
- Operator dashboard with live run submission and evidence timeline.
- FastAPI endpoints for runs and diff analysis.

## Safety
This project does not claim OS-level sandboxing. Production execution of untrusted repositories should use disposable containers or VMs, resource quotas and restricted networking.

## Run
API: cd apps/api, install the dev extra, then run uvicorn app.main:app --reload.
Web: cd apps/web, install dependencies, then run npm run dev.
Set NEXT_PUBLIC_API_URL when the web and API are on different hosts.
