# Architecture Overview

## Control Loop

`User Request → Repository Understanding → Task Decomposition → Dependency-Aware Plan → Cryptographic Approval → Durable Operation Journaling → Guarded Tool Execution → Independent Step Verification → Disciplined Self-Correction → Final Evidence Report`

The API accepts a typed `TaskSpec`, retrieves sanitized repository context with symbol and test mappings, decomposes the request into an inspectable DAG with explicit preconditions and postconditions, requests only allowlisted tools, and records persistent step checkpoints and durable Operation Journal records in SQLite Write-Ahead Logging (WAL).

---

## Safety Boundary

The model is advisory, not privileged:
1. Model suggestions must conform to strict Pydantic schemas with `extra="forbid"`.
2. The policy layer authorizes every tool call before invocation.
3. Mutations default to dry-run; real modifications compute cryptographic fingerprints and require explicit operator approval.
4. Commands execute shell-free (`shell=False`) with strict timeouts, output limits, and process tree termination (`_kill_process_tree`).
5. Filesystem operations reject path traversal, symlink escapes, UNC paths, drive prefixes, and NTFS alternate data streams.
6. Multi-stage verification produces structured, machine-readable evidence (`step_id`, `category`, `expected`, `actual`, `timestamp`) and cannot be overridden by model assertions.
7. Anti-cycling detection halts repetitive repair loops with `STRATEGY_LOOP`.
8. Complete cancellation support is wired through REST API, WebSocket streams, and the CLI.

> **Important:** This is application-level execution safety, not an OS-level sandbox. Untrusted repositories should be run within disposable containers or VMs.

---

## Execution Lifecycle

```text
       ┌──────────┐
       │  INTAKE  │
       └────┬─────┘
            ▼
       ┌────────────────────────┐
       │ CRASH RECONCILIATION   ├──────────────────────────┐
       └────┬───────────────────┘                          │
            ▼ (clean / reconciled)                         ▼ (corrupted / hash diverged)
       ┌──────────┐                             ┌───────────────────────────┐
       │ PLANNING │                             │  RECONCILIATION_REQUIRED  │
       └────┬─────┘                             └───────────────────────────┘
            │
            ├──────────────────────────────────────────┐
            ▼ (if mutating action & not auto-approved) │
 ┌──────────────────────────────────┐                  │
 │       AWAITING_APPROVAL          │                  │
 │ (Cryptographic Hash Fingerprint) │                  │
 └──────────┬───────────────────────┘                  │
            │ (approved via /resume matching hash)     │
            ▼                                          ▼
       ┌──────────┐                            ┌────────────┐
       │EXECUTING ├───────────────────────────▶│   FAILED   │
       └────┬─────┘ (unrecoverable / cancelled) └────────────┘
            ▼                                          ▲
       ┌──────────┐                                    │
       │VERIFYING ├────────────────────────────────────┤
       └────┬─────┘ (verification gate failed)         │
            ▼                                          │
       ┌──────────────┐                                │
       │SELF-CORRECT  ├────────────────────────────────┘
       │(Anti-Cycling)│ (strategy loop or budget exhausted)
       └────┬─────────┘
            ▼ (all gates green)
       ┌──────────┐
       │COMPLETED │
       └──────────┘
```

---

## Verification Framework

Every verification check produces a structured, step-linked `VerificationResult`:

| Field | Type | Description |
|---|---|---|
| `check` | `str` | Name of the verification check (e.g., `syntax:app.py`, `tool_allowlist`) |
| `passed` | `bool` | Deterministic outcome of the check |
| `detail` | `str` | Diagnostic explanation or failure trace |
| `step_id` | `str?` | Identifier of the associated plan step |
| `category` | `str?` | Category (`syntax`, `proof_of_test`, `security_critic`, `boundary`) |
| `expected` | `str?` | Explicit expected state |
| `actual` | `str?` | Observed actual state on disk |
| `timestamp`| `str?` | ISO-8601 UTC timestamp of execution |

---

## Independent Evaluation Benchmark Suite V2

The system features 20 automated benchmark scenarios:

1. `eval-01-success`: Valid task in clean workspace.
2. `eval-02-ambiguous`: Ambiguous task intent normalized safely.
3. `eval-03-missing-deps`: Missing external dependencies handled gracefully.
4. `eval-04-invalid-tool-args`: Rejection of schema-invalid tool parameters.
5. `eval-05-tool-timeout`: Enforcement of hard execution timeouts.
6. `eval-06-api-failures`: Fallback to deterministic execution when advisory LLM fails.
7. `eval-07-prompt-injection`: Sanitization of prompt-injection in repository files.
8. `eval-08-policy-bypass`: Gating and rejection of unapproved tools.
9. `eval-09-regression-detection`: Missing critical modules flagged as regression.
10. `eval-10-honest-failure`: Agent admits failure truthfully rather than fabricating success.
11. `eval-11-crash-recovery`: Interrupted operations reconciled using postcondition hashes.
12. `eval-12-idempotent-replay`: Duplicate operation skipping via journal idempotency keys.
13. `eval-13-approval-enforcement`: Mutations halt at `AWAITING_APPROVAL`.
14. `eval-14-filesystem-escape`: Path traversal outside workspace rejected.
15. `eval-15-oversized-output`: Stream truncation prevents context memory blowout.
16. `eval-16-approval-invalidation`: Plan/diff divergence invalidates approval request.
17. `eval-17-run-cancellation`: Clean task cancellation and process abort.
18. `eval-18-strategy-loop-detection`: Anti-cycling halts repeated identical repair attempts.
19. `eval-19-false-positive-verification`: Rejection of tests with zero assertions.
20. `eval-20-duplicate-run-guard`: Re-entrant concurrency lock guards against race conditions.
