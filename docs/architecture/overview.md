# Architecture Overview

## Control Loop

`Observe → Plan → Act → Verify → Reflect → Report`

The API accepts a `TaskSpec`, builds a bounded plan, requests only allowlisted tools, and records explicit run events.

## Safety Boundary

The model is not a privileged process. A future model provider will request a tool invocation; the policy layer authorizes it; only then may a registered tool execute.

Verification remains independent from model-generated text.

## Lifecycle

```text
INTAKE → PLANNING → EXECUTING → VERIFYING → REFLECTING → COMPLETED
                         │             │
                         └─────────────┴──→ FAILED
```

## Planned Evolution

1. Repository indexing and semantic context
2. Sandboxed patch generation
3. Real command execution with resource limits
4. LLM provider adapters
5. Code-review agent
6. GitHub PR lifecycle integration
7. Persistent run/event store
8. Multi-agent specialization and evaluation
