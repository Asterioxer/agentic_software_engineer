from __future__ import annotations

import json
from pathlib import Path

from app.evaluation import (
    SWEBenchInstance,
    SWEBenchRunner,
)


def _setup_mock_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(
        "[project]\nname = 'calc'\nversion = '0.1.0'\n", encoding="utf-8"
    )
    src = path / "src"
    src.mkdir()
    (src / "math_ops.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8"
    )
    tests = path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(
        "from src.math_ops import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )


def test_swe_bench_evaluation_lifecycle(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _setup_mock_repo(repo)

    runner = SWEBenchRunner(output_dir=str(tmp_path / "reports"))

    instance = SWEBenchInstance(
        instance_id="repo__calc-001",
        repo="calc",
        problem_statement="Ensure add function works correctly and passes all test suites",
        fail_to_pass=("test_add",),
        pass_to_pass=(),
    )

    result = runner.evaluate_instance(instance, workspace_dir=repo, auto_approve=True)
    assert result.instance_id == "repo__calc-001"
    assert result.resolved
    assert result.fail_to_pass_passed
    assert result.duration_seconds > 0.0


def test_swe_bench_runner_benchmark_aggregation(tmp_path: Path) -> None:
    repo = tmp_path / "repo2"
    _setup_mock_repo(repo)

    reports_dir = tmp_path / "swe_reports"
    runner = SWEBenchRunner(output_dir=str(reports_dir))

    instances = [
        SWEBenchInstance(
            instance_id="repo__calc-001",
            repo="calc",
            problem_statement="Run tests for calculator add",
        ),
    ]

    report = runner.run_benchmark(instances, workspace_dir=repo)
    assert report.total_instances == 1
    assert report.resolved_instances == 1
    assert report.resolve_rate == 1.0

    # Verify JSON report written
    out_file = reports_dir / "swe_bench_report.json"
    assert out_file.exists()
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["resolve_rate"] == 1.0
    assert len(saved["results"]) == 1
