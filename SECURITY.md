# Security Policy

## Scope

This repository contains an agentic software-engineering prototype that can inspect repositories and execute bounded local actions.

## Important boundary

The application-level command boundary is **not** a substitute for OS-level sandboxing.

Do not point the executor at hostile repositories and enable real mutation without an additional isolation layer.

For production deployments, use:
- disposable containers or VMs;
- CPU and memory quotas;
- read-only base images where possible;
- restricted filesystem mounts;
- restricted outbound networking;
- short-lived credentials;
- explicit operator approval for destructive actions.

## Reporting

For a suspected security issue, do not include secrets or private repository contents in a public issue. Contact the repository owner privately first.
