# Portfolio Showcase

## One-line pitch

**Agentic Software Engineer is a safety-first coding-agent control plane that turns repository tasks into bounded, auditable engineering runs instead of unrestricted LLM shell sessions.**

## 30-second explanation

I built an agentic software-engineering system around an explicit control loop: observe the repository, build a plan, pass every tool call through policy, execute bounded actions, independently verify the result, and reflect on failures.

The key engineering decision was separating **probabilistic planning** from **deterministic execution and verification**. The system can use a local Ollama model for advisory planning, but the model never becomes the security boundary.

## Architecture story

**Repository → Context → Plan → Policy → Execution → Verification → Evidence**

The architecture is intentionally modular:

- repository intelligence is deterministic;
- tools are typed and allowlisted;
- workspace mutation is dry-run by default;
- shell execution is replaced by structured command IDs;
- verification is independent from planning;
- reflection has an explicit retry budget;
- model providers can be swapped without changing the execution boundary.

## Strong interview questions

### Why build this instead of a coding chatbot?

A chatbot generates suggestions. This project explores the harder systems problem: how an engineering agent can operate on a real repository while remaining bounded, observable and verifiable.

### How did you handle agent safety?

I avoided treating the LLM as a trusted process. Commands are allowlisted, shell interpolation is disabled, execution has timeout/output limits, workspace paths are root-checked, and verification produces independent evidence.

### How do you prevent false success?

The planner cannot directly declare success. The verification pipeline evaluates workspace artifacts and command results separately. Failed evidence is propagated into the run state.

### Why is the local model optional?

The deterministic system should remain useful without an API key. Ollama is an advisory provider, not a prerequisite for the control plane.

### What is still missing?

True OS/container isolation for hostile repositories, persistent run storage, richer code intelligence, semantic retrieval, and fully automated GitHub mutations behind explicit operator approval.

## Suggested demo flow

1. Open the operator dashboard.
2. Submit a repository-aware task.
3. Show the generated plan and lifecycle events.
4. Show verification evidence rather than only a final "success" message.
5. Call the diff-analysis endpoint with a sample patch.
6. Explain the command allowlist and why arbitrary shell access is intentionally absent.
7. Optionally enable Ollama and demonstrate provider fallback.
