from pathlib import Path

from app.evaluation.dataset import get_standard_evaluation_scenarios
from app.evaluation.evaluator import IndependentEvaluator


def test_standard_evaluation_suite_covers_all_categories() -> None:
    scenarios = get_standard_evaluation_scenarios()
    categories = {s.category.value for s in scenarios}
    assert len(scenarios) == 25
    assert "successful_coding" in categories
    assert "ambiguous_task" in categories
    assert "missing_dependencies" in categories
    assert "invalid_tool_args" in categories
    assert "tool_timeout" in categories
    assert "api_failures" in categories
    assert "prompt_injection" in categories
    assert "policy_bypass" in categories
    assert "regression_detection" in categories
    assert "honest_failure" in categories
    assert "crash_recovery" in categories
    assert "idempotent_replay" in categories
    assert "approval_enforcement" in categories
    assert "filesystem_escape" in categories
    assert "oversized_output" in categories
    assert "approval_invalidation" in categories
    assert "run_cancellation" in categories
    assert "strategy_loop_detection" in categories
    assert "false_positive_verification" in categories
    assert "duplicate_run_guard" in categories
    assert "toctou_defense" in categories
    assert "approval_expiration" in categories
    assert "symlink_defense" in categories
    assert "vcs_patch_defense" in categories
    assert "circular_dependency_detection" in categories


def test_independent_evaluator_runs_and_generates_report(tmp_path: Path) -> None:
    evaluator = IndependentEvaluator(output_dir=str(tmp_path))
    scenarios = get_standard_evaluation_scenarios()
    report = evaluator.run_all(scenarios)

    assert report.total_scenarios == 25
    assert report.passed_scenarios == 25
    assert report.pass_rate == 1.0
    assert report.policy_adherence_rate == 1.0
    assert report.truthfulness_rate == 1.0

    report_json = tmp_path / "evaluation_report.json"
    assert report_json.exists()
    assert '"truthfulness_rate": 1.0' in report_json.read_text(encoding="utf-8")

    md_report = tmp_path / "evaluation_summary.md"
    assert md_report.exists()
    assert "# Independent Evaluation Report V2" in md_report.read_text(encoding="utf-8")
