# Architecture Overview

## Control Loop

`User Request → Repository Understanding → Task Decomposition → Execution Plan → Operator Approval → Guarded Execution → Independent Verification → Failure Diagnosis → Evidence-Based Report`

The API accepts a typed `TaskSpec`, retrieves sanitized repository context, decomposes the request into inspectable steps, requests only allowlisted tools, and records persistent step checkpoints and audit evidence.

## Safety Boundary

The model is advisory, not privileged:
1. Model suggestions must conform to strict Pydantic schemas.
2. The policy layer authorizes every tool call before invocation.
3. Mutations default to dry-run; real modifications require explicit operator approval.
4. Commands execute shell-free (`shell=False`) with strict timeouts and output limits.
5. Verification independently produces structured evidence and cannot be overridden by model assertions.

> **Important:** This is application-level execution safety, not an OS-level sandbox. Untrusted repositories should be run within disposable containers or VMs.

## Execution Lifecycle

```text
       ┌──────────┐
       │  INTAKE  │
       └────┬─────┘
            ▼
       ┌──────────┐
       │ PLANNING │
       └────┬─────┘
            │
            ├──────────────────────────────────────────┐
            ▼ (if mutating action & not auto-approved) │
 ┌──────────────────────┐                             │
 │  AWAITING_APPROVAL   │                             │
 └──────────┬───────────┘                             │
            │ (approved via /resume)                   │
            ▼                                         ▼
       ┌──────────┐                            ┌────────────┐
       │EXECUTING ├───────────────────────────▶│   FAILED   │
       └────┬─────┘ (unrecoverable / budget 0) └────────────┘
            ▼                                         ▲
       ┌──────────┐                                   │
       │VERIFYING ├───────────────────────────────────┤
       └────┬─────┘ (verification gate failed)        │
            ▼                                         │
       ┌──────────┐                                   │
       │REFLECTING├───────────────────────────────────┘
       └────┬─────┘
            ▼ (all gates green)
       ┌──────────┐
       │COMPLETED │
       └──────────┘
```

## Core Subsystems

1. **Repository Intelligence & Sanitized Code Context (`repository.py`, `code_context.py`)**:
   Bounded file traversal, symbol extraction (Python & TypeScript), and prompt-injection defanging.
2. **Persistent Checkpoint Store (`store.py`)**:
   Thread-safe SQLite storage for runs, step checkpoints, timeline events, and tool execution evidence.
3. **Guardrails & Execution Boundary (`policy.py`, `execution.py`, `command_runner.py`)**:
   Strict tool allowlist, path traversal defenses, risk classification, and command sandboxing.
4. **Independent Verification Pipeline (`verification.py`, `verification_pipeline.py`)**:
   External checks verifying expected artifacts and git diff whitespace integrity.
5. **Failure Classification & Reflection (`reflection.py`)**:
   Categorizes errors (`POLICY_VIOLATION`, `TIMEOUT`, `SYNTAX_ERROR`, `DEPENDENCY_MISSING`, `VALIDATION_FAILURE`) with bounded retry budgets.
6. **Independent Evaluation Harness (`evaluation/`)**:
   10-scenario benchmark suite evaluating task completion, policy adherence, truthfulness, and failure admission.
