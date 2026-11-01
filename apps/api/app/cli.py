from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .critic import review_diff, review_workspace
from .domain import RunStatus, TaskSpec
from .evaluation import IndependentEvaluator
from .policy import ToolPolicy
from .repository_service import summarize_repository
from .runner import AgentRun, resume_run
from .store import RunStore, get_default_store
from .tools import build_default_registry


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format a clean plain-text ASCII table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    header_str = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep_str = "-+-".join("-" * widths[i] for i in range(len(headers)))
    row_strs = [" | ".join(str(val).ljust(widths[i]) for i, val in enumerate(row)) for row in rows]
    return f"{header_str}\n{sep_str}\n" + "\n".join(row_strs)


def cmd_run(args: argparse.Namespace) -> int:
    registry = build_default_registry()
    policy = ToolPolicy()
    store = RunStore(args.db) if args.db else get_default_store()

    task = TaskSpec(
        title=args.title,
        description=args.desc or args.title,
        repository=args.repo,
        dry_run=not args.no_dry_run,
        auto_approve=args.auto_approve,
    )

    print(f"\n[Autonomous Coding Agent] Dispatching task: '{task.title}'")
    if task.repository:
        print(f"  Target Repository: {task.repository}")
    print(f"  Mode: {'DRY-RUN (Safe preview)' if task.dry_run else 'REAL MUTATION'}")
    print(
        f"  Approval Gating: {'Auto-approved' if task.auto_approve else 'Explicit approval required'}\n"
    )

    run = AgentRun(task, registry, policy, store=store)
    result = run.execute()
    status = str(result.get("status", "unknown"))

    print(f"Run ID: {run.run_id}")
    print(f"Execution Status: {status.upper()}")

    plan = result.get("plan", [])
    if isinstance(plan, list) and plan:
        print("\nPlan Steps:")
        step_rows = []
        for s in plan:
            if isinstance(s, dict):
                step_rows.append(
                    [
                        str(s.get("id")),
                        str(s.get("tool") or "internal"),
                        str(s.get("status", "pending")),
                        str(s.get("description", ""))[:50],
                    ]
                )
        print(format_table(["Step ID", "Tool", "Status", "Description"], step_rows))

    verification = result.get("verification", [])
    if isinstance(verification, list) and verification:
        print("\nVerification Checks:")
        v_rows = []
        for v in verification:
            if isinstance(v, dict):
                icon = "PASS" if v.get("passed") else "FAIL"
                v_rows.append([icon, str(v.get("check")), str(v.get("detail", ""))[:60]])
        print(format_table(["Result", "Check", "Detail"], v_rows))

    if status == RunStatus.COMPLETED.value:
        print("\n=> Result: Task COMPLETED successfully with all verification gates passed.")
        return 0
    elif status == RunStatus.AWAITING_APPROVAL.value:
        print(
            f"\n=> Result: AWAITING OPERATOR APPROVAL. Resume with: python -m app.cli resume {run.run_id} --approve"
        )
        return 2
    else:
        diag = result.get("failure_diagnosis")
        if isinstance(diag, dict):
            print(f"\nFailure Diagnosed: [{diag.get('category')}] {diag.get('message')}")
            print(f"Suggested Recovery: {diag.get('suggested_recovery')}")
        print("\n=> Result: Task FAILED.")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    store = RunStore(args.db) if args.db else get_default_store()
    checkpoint = store.get_checkpoint(args.run_id)
    if not checkpoint:
        print(f"Error: Run '{args.run_id}' not found.")
        return 1

    print(f"\n[Run Checkpoint: {checkpoint.run_id}]")
    print(f"Status: {checkpoint.status.value.upper()}")
    print(f"Task: {checkpoint.task.title}")
    if checkpoint.task.repository:
        print(f"Repository: {checkpoint.task.repository}")

    # Operations journal
    ops = store.list_operations_for_run(args.run_id)
    if ops:
        print(f"\nDurable Operations ({len(ops)}):")
        op_rows = []
        for op in ops:
            op_rows.append(
                [
                    op.operation_id,
                    op.step_id,
                    op.tool,
                    op.state.value,
                    str(op.execution_attempt),
                    op.recovery_status or op.idempotency_key[:8],
                ]
            )
        print(format_table(["Op ID", "Step", "Tool", "State", "Attempt", "Status/Key"], op_rows))

    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    store = RunStore(args.db) if args.db else get_default_store()
    try:
        res = resume_run(args.run_id, approved=args.approve, store=store)
        status = str(res.get("status", "unknown"))
        print(f"Resumed Run: {args.run_id}")
        print(f"New Status: {status.upper()}")
        return 0 if status == RunStatus.COMPLETED.value else 1
    except ValueError as exc:
        print(f"Error resuming run: {exc}")
        return 1


def cmd_benchmark(args: argparse.Namespace) -> int:
    print("\n[Autonomous Coding Benchmark Suite V2]")
    evaluator = IndependentEvaluator(output_dir=args.out)
    report = evaluator.run_all()

    print(
        f"\nBenchmark Complete: {report.passed_scenarios}/{report.total_scenarios} passed ({report.pass_rate * 100:.1f}%)"
    )
    print(f"Policy Adherence: {report.policy_adherence_rate * 100:.1f}%")
    print(f"Truthfulness Rate: {report.truthfulness_rate * 100:.1f}%\n")

    sc_rows = []
    for sc in report.scenarios:
        sc_rows.append(
            [
                sc.scenario_id,
                sc.category,
                "PASS" if sc.passed else "FAIL",
                sc.actual_status,
                sc.details[0][:40] if sc.details else "",
            ]
        )
    print(format_table(["Scenario", "Category", "Result", "Status", "Detail"], sc_rows))
    return 0 if report.pass_rate == 1.0 else 1


def cmd_review(args: argparse.Namespace) -> int:
    path = Path(args.target)
    if not path.exists():
        print(f"Error: Target '{args.target}' does not exist.")
        return 1

    content = path.read_text(encoding="utf-8")
    if "--- " in content and "+++ " in content:
        # Unified diff
        print(f"\n[Security Critic: Reviewing Unified Diff '{args.target}']")
        review = review_diff(content)
    else:
        # File scan
        print(f"\n[Security Critic: Reviewing File '{args.target}']")
        review = review_workspace(str(path.parent), [path.name])

    print(f"Decision: {'APPROVED' if review.approved else 'REJECTED'}")
    print(f"Risk Score: {review.risk_score}")
    print(f"Summary: {review.summary}")

    if review.findings:
        print("\nFindings:")
        f_rows = []
        for f in review.findings:
            f_rows.append([f.rule_id, f.severity, str(f.line_number or "-"), f.description[:50]])
        print(format_table(["Rule", "Severity", "Line", "Description"], f_rows))

    return 0 if review.approved else 1


def cmd_inspect(args: argparse.Namespace) -> int:
    summary = summarize_repository(args.repo)
    print(f"\n[Repository Intelligence: {summary.get('root')}]")
    print(f"File Count: {summary.get('file_count')}")
    print(f"Languages: {summary.get('languages')}")
    print(f"Detected Frameworks: {summary.get('frameworks')}")
    manifests = summary.get("manifests", {})
    if manifests:
        print("Manifests:")
        for m_name, m_info in manifests.items():
            deps = m_info.get("dependencies", [])
            print(f"  - {m_name} ({len(deps)} deps)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-engineer",
        description="Autonomous Software Engineering Agent CLI - Guarded, Auditable, Deterministic.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Dispatch an autonomous software engineering task")
    p_run.add_argument("title", help="Task title")
    p_run.add_argument("--desc", help="Detailed description and constraints", default=None)
    p_run.add_argument("--repo", help="Path to repository", default=None)
    p_run.add_argument(
        "--no-dry-run",
        help="Apply actual workspace mutations (requires approval or auto-approve)",
        action="store_true",
    )
    p_run.add_argument("--auto-approve", help="Auto-approve mutations", action="store_true")
    p_run.add_argument("--db", help="Path to SQLite database", default=None)
    p_run.set_defaults(func=cmd_run)

    # status
    p_status = subparsers.add_parser(
        "status", help="Inspect execution status and journal for a run"
    )
    p_status.add_argument("run_id", help="Run ID")
    p_status.add_argument("--db", help="Path to SQLite database", default=None)
    p_status.set_defaults(func=cmd_status)

    # resume
    p_resume = subparsers.add_parser(
        "resume", help="Resume an existing paused or awaiting approval run"
    )
    p_resume.add_argument("run_id", help="Run ID")
    p_resume.add_argument(
        "--approve",
        help="Grant explicit operator approval to execute mutations",
        action="store_true",
    )
    p_resume.add_argument("--db", help="Path to SQLite database", default=None)
    p_resume.set_defaults(func=cmd_resume)

    # benchmark
    p_bench = subparsers.add_parser(
        "benchmark", help="Run independent 15-scenario evaluation benchmark suite"
    )
    p_bench.add_argument("--out", help="Output directory for reports", default="evaluation_reports")
    p_bench.set_defaults(func=cmd_benchmark)

    # review
    p_review = subparsers.add_parser(
        "review", help="Run automated Security Critic on a diff or source file"
    )
    p_review.add_argument("target", help="Path to diff or file")
    p_review.set_defaults(func=cmd_review)

    # inspect
    p_inspect = subparsers.add_parser(
        "inspect", help="Extract repository intelligence, frameworks, and manifests"
    )
    p_inspect.add_argument("repo", help="Path to repository")
    p_inspect.set_defaults(func=cmd_inspect)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func:
        return int(func(args))
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
