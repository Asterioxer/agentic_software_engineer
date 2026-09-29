# Agent Control Loop

## State machine

INTAKE → PLANNING → EXECUTING → VERIFYING → REFLECTING → COMPLETED

Any policy, repository-inspection, execution or verification failure can transition the run to FAILED.

## Design invariant

No probabilistic component is required to establish the safety boundary.

The model can propose. Policy decides. Executors enforce. Verification evaluates.

## Evidence

A run returns:
- plan;
- repository summary when applicable;
- tool results;
- verification results;
- ordered lifecycle events.

This makes the run inspectable instead of treating the agent as a black box.
