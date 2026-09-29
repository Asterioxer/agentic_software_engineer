# Verification Pipeline

Verification is independent from planning. A plan can claim success; verification must produce its own evidence.

The pipeline combines expected workspace artifact checks with git diff --check. Each result contains a stable check name, pass/fail state and diagnostic detail. A run passes only when every required verification result passes.
