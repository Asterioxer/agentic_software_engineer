#!/usr/bin/env python3
"""Reproducible End-to-End Demonstrations for Autonomous Coding Agent.

Demonstrates:
  Demo A: Full lifecycle with operator approval, durable journaling, and independent verification.
  Demo B: Truthful refusal and honest failure handling without fabricating success.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Add api package to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "apps" / "api"))

from app.domain import RunStatus, TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun, resume_run
from app.store import RunStore
from app.tools import build_default_registry


def setup_calculator_repo(temp_dir: Path) -> Path:
    """Create a realistic sample repository with Git initialization."""
    repo = temp_dir / "calc_service"
    repo.mkdir(parents=True, exist_ok=True)

    src_dir = repo / "src"
    src_dir.mkdir(exist_ok=True)
    tests_dir = repo / "tests"
    tests_dir.mkdir(exist_ok=True)

    (src_dir / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )
    (tests_dir / "test_calculator.py").write_text(
        "from src.calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "calc-service"\nversion = "0.1.0"\ndependencies = ["pytest>=8.0"]\n',
        encoding="utf-8",
    )
    (repo / "README.md").write_text("# Calculator Service\n", encoding="utf-8")

    # Initialize Git
    try:
        subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Agent Demo"], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "demo@antigravity.local"], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), check=True, capture_output=True)
    except Exception as exc:
        print(f"Warning: Git init skipped ({exc})")

    return repo


def run_demo_a(temp_dir: Path) -> dict[str, object]:
    """Demo A: Successful Feature Addition with Operator Approval & Durable Journaling."""
    print("\n" + "=" * 70)
    print("DEMO A: SUCCESSFUL CODING TASK WITH OPERATOR APPROVAL & JOURNALING")
    print("=" * 70)

    repo = setup_calculator_repo(temp_dir)
    store = RunStore(str(temp_dir / "demo_a.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    # Step 1: Intake & Planning with dry_run=False (requires operator approval)
    task = TaskSpec(
        title="Add multiply function to calculator",
        description="Implement multiply(a, b) in src/calculator.py and add unit test in tests/test_calculator.py",
        repository=str(repo),
        dry_run=False,
        auto_approve=False,
    )

    print("\n[Phase 1: Task Intake & Initial Execution]")
    run = AgentRun(task, registry, policy, store=store)
    result = run.execute()

    print(f"  Status: {result['status']}")
    assert result["status"] == RunStatus.AWAITING_APPROVAL.value, "Must pause for approval"
    print("  => Correctly halted at execution boundary: mutation requires operator sign-off.")

    # Inspect planned steps
    plan = result.get("plan", [])
    print(f"  Plan steps generated: {len(plan)}")
    for s in plan:
        tool_desc = f"tool={s.get('tool')}" if s.get("tool") else "no tool"
        print(f"    - [{s.get('id')}]: {s.get('description')} ({tool_desc})")

    # Step 2: Operator reviews diff and grants explicit approval
    print("\n[Phase 2: Operator Approval & Execution Resumption]")
    resumed = resume_run(
        run_id=run.run_id,
        approved=True,
        registry=registry,
        policy=policy,
        store=store,
    )

    print(f"  Resumed Status: {resumed['status']}")
    assert resumed["status"] == RunStatus.COMPLETED.value, "Must complete after approval"
    print("  => Successfully executed approved mutations and passed all verification gates.")

    # Step 3: Inspect Durable Operation Journal
    ops = store.list_operations_for_run(run.run_id)
    print(f"\n[Phase 3: Durable Operation Journal Records ({len(ops)} operations)]")
    for op in ops:
        print(f"  - Op ID: {op.operation_id} | Step: {op.step_id} | State: {op.state.value} | Key: {op.idempotency_key[:8]}...")
        if op.postcondition_hash:
            print(f"    Postcondition Hash: {op.postcondition_hash[:16]}...")

    # Step 4: Inspect Independent Verification Evidence
    checks = resumed.get("verification", [])
    print(f"\n[Phase 4: Independent Verification Evidence ({len(checks)} checks)]")
    for c in checks:
        icon = "PASS" if c.get("passed") else "FAIL"
        print(f"  - [{icon}] {c.get('check')}: {c.get('detail')}")

    return resumed


def run_demo_b(temp_dir: Path) -> dict[str, object]:
    """Demo B: Honest Refusal & Truthful Failure Reporting."""
    print("\n" + "=" * 70)
    print("DEMO B: HONEST FAILURE & TRUTHFUL REFUSAL (NO FALSE CLAIMS)")
    print("=" * 70)

    repo = setup_calculator_repo(temp_dir)
    store = RunStore(str(temp_dir / "demo_b.db"))
    registry = build_default_registry()
    policy = ToolPolicy()

    # Impossible task: verify nonexistent artifact
    task = TaskSpec(
        title="Verify nonexistent quantum computing engine",
        description="Run verification on quantum_module.py which does not exist.",
        repository=str(repo),
        expected_files=["src/nonexistent_quantum_engine.py"],
        dry_run=True,
        auto_approve=False,
    )

    print("\n[Phase 1: Task Execution with Impossible Verification Requirement]")
    run = AgentRun(task, registry, policy, store=store)
    result = run.execute()

    print(f"  Status: {result['status']}")
    assert result["status"] == RunStatus.FAILED.value, "Must admit failure"
    print("  => Correctly admitted failure instead of fabricating false completion.")

    # Step 2: Inspect Structured Failure Diagnosis
    diag = result.get("failure_diagnosis")
    print("\n[Phase 2: Structured Failure Classification]")
    if isinstance(diag, dict):
        print(f"  Category: {diag.get('category')}")
        print(f"  Message: {diag.get('message')}")
        print(f"  Recoverable: {diag.get('recoverable')}")
        print(f"  Suggested Recovery: {diag.get('suggested_recovery')}")

    # Step 3: Inspect Verification Details
    checks = result.get("verification", [])
    print(f"\n[Phase 3: Verification Audit ({len(checks)} checks)]")
    for c in checks:
        icon = "PASS" if c.get("passed") else "FAIL"
        print(f"  - [{icon}] {c.get('check')}: {c.get('detail')}")

    return result


def main() -> None:
    temp_dir = Path(tempfile.mkdtemp(prefix="agentic_demo_"))
    try:
        demo_a_result = run_demo_a(temp_dir)
        demo_b_result = run_demo_b(temp_dir)

        print("\n" + "=" * 70)
        print("DEMONSTRATION SCOREBOARD")
        print("=" * 70)
        print(f"Demo A (Approved Execution): {demo_a_result['status'].upper()}")
        print(f"Demo B (Honest Failure Refusal): {demo_b_result['status'].upper()}")
        print("\nAll demonstration requirements verified successfully without synthetic shortcuts.\n")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
