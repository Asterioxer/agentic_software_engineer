# Repository Intelligence

Repository intelligence is deliberately deterministic before an LLM is introduced.

## Responsibilities

1. Enumerate repository files.
2. Ignore generated/dependency directories.
3. Classify common languages.
4. Bound traversal to a maximum file count.
5. Produce a compact summary suitable for later agent planning.

The next stage can layer symbol extraction, dependency graphs, semantic search, and Git history without changing the agent control loop.
