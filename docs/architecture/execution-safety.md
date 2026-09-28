# Execution Safety

Planning and mutation are separate boundaries.

- Workspace actions are dry-run by default.
- Paths are resolved against a configured repository root.
- Parent-directory traversal is rejected.
- Action counts are bounded.
- Only explicit write/delete operations are accepted.
- Verification is independent from the executor.

A future command runner will add process isolation, timeouts, environment filtering, and resource limits.
