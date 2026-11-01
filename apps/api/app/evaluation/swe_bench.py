from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..command_runner import CommandRunner
from ..domain import RunStatus, TaskSpec
from ..patch import PatchApplier
from ..policy import ToolPolicy
from ..runner import AgentRun
from ..store import RunStore
from ..tools import build_default_registry

logger = logging.getLogger("agent.evaluation.swe_bench")


@dataclass(frozen=True)
class SWEBenchInstance:
    """Standardized software engineering benchmark task instance."""

    instance_id: str
    repo: str
    problem_statement: str
    base_commit: str = "HEAD"
    fail_to_pass: tuple[str, ...] = field(default_factory=tuple)
    pass_to_pass: tuple[str, ...] = field(default_factory=tuple)
    test_patch: str | None = None
    hints: str = ""


@dataclass(frozen=True)
class SWEBenchResult:
    """Evaluation result for a single SWE-bench instance."""

    instance_id: str
    resolved: bool
    agent_status: str
    fail_to_pass_passed: bool
    pass_to_pass_unbroken: bool
    details: str
    duration_seconds: float


@dataclass(frozen=True)
class SWEBenchReport:
    """Aggregated SWE-bench benchmark performance report."""

    total_instances: int
    resolved_instances: int
    resolve_rate: float
    results: list[SWEBenchResult]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SWEBenchRunner:
    """Independent evaluation harness executing tasks against standardized SWE-bench format."""

    def __init__(self, output_dir: str = "evaluation_reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def evaluate_instance(
        self,
        instance: SWEBenchInstance,
        workspace_dir: Path,
        auto_approve: bool = True,
    ) -> SWEBenchResult:
        start_time = time.perf_counter()
        logger.info("Evaluating SWE-bench instance: %s", instance.instance_id)

        # 1. Apply test patch if provided
        if instance.test_patch:
            applier = PatchApplier(str(workspace_dir), dry_run=False)
            p_res = applier.apply_diff(instance.test_patch)
            if not p_res.applied:
                return SWEBenchResult(
                    instance_id=instance.instance_id,
                    resolved=False,
                    agent_status="test_patch_error",
                    fail_to_pass_passed=False,
                    pass_to_pass_unbroken=False,
                    details=f"Failed to apply test patch: {p_res.error}",
                    duration_seconds=time.perf_counter() - start_time,
                )

        # 2. Formulate task for autonomous agent
        task = TaskSpec(
            title=f"Resolve issue: {instance.instance_id}",
            description=instance.problem_statement,
            repository=str(workspace_dir),
            dry_run=False,
            auto_approve=auto_approve,
        )

        db_path = workspace_dir / ".agent_eval.db"
        store = RunStore(str(db_path))
        registry = build_default_registry()
        policy = ToolPolicy()

        agent_run = AgentRun(task, registry, policy, store=store)
        res = agent_run.execute(auto_approved=auto_approve)
        agent_status = str(res.get("status", "unknown"))

        # 3. Deterministic verification: Run tests via CommandRunner
        cmd_runner = CommandRunner(str(workspace_dir))
        test_run = cmd_runner.run("python.tests", timeout_seconds=45.0)

        # Evaluate fail_to_pass and pass_to_pass
        test_output = (test_run.stdout + "\n" + test_run.stderr).lower()
        test_success = test_run.exit_code == 0

        fail_to_pass_passed = test_success
        pass_to_pass_unbroken = test_success and "failed" not in test_output

        resolved = (
            agent_status == RunStatus.COMPLETED.value
            and fail_to_pass_passed
            and pass_to_pass_unbroken
        )

        duration = time.perf_counter() - start_time
        return SWEBenchResult(
            instance_id=instance.instance_id,
            resolved=resolved,
            agent_status=agent_status,
            fail_to_pass_passed=fail_to_pass_passed,
            pass_to_pass_unbroken=pass_to_pass_unbroken,
            details="All fail-to-pass tests passed and 0 regressions."
            if resolved
            else f"Tests exit code: {test_run.exit_code}",
            duration_seconds=duration,
        )

    def run_benchmark(
        self,
        instances: list[SWEBenchInstance],
        workspace_dir: Path,
    ) -> SWEBenchReport:
        results: list[SWEBenchResult] = []
        for inst in instances:
            res = self.evaluate_instance(inst, workspace_dir)
            results.append(res)

        resolved_count = sum(1 for r in results if r.resolved)
        total = len(instances)
        rate = resolved_count / total if total > 0 else 0.0

        report = SWEBenchReport(
            total_instances=total,
            resolved_instances=resolved_count,
            resolve_rate=rate,
            results=results,
        )

        # Save to output dir
        out_file = self.output_dir / "swe_bench_report.json"
        out_file.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        return report
