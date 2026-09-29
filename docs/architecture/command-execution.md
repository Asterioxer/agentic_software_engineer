# Command Execution Safety

The command layer is deliberately structured rather than an arbitrary shell.

- Commands use stable IDs and an explicit allowlist.
- subprocess execution uses shell=False.
- The working directory is the resolved repository root.
- The environment is reduced to deterministic variables.
- Execution has a hard timeout cap of 60 seconds.
- Captured output is capped at 32 KiB per stream.
- Non-zero exit codes and timeouts become verification evidence.

Current command IDs:
- python.tests: python -m pytest
- python.compile: python -m compileall
- git.diff.check: git diff --check

This is bounded command execution, not OS-level sandboxing. Production deployments should add container/process isolation for untrusted repositories.
