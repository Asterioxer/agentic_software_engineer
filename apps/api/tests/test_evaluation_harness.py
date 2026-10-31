from pathlib import Path

from app.evaluation.dataset import get_standard_evaluation_scenarios
from app.evaluation.evaluator import IndependentEvaluator


def test_standard_evaluation_suite_covers_all_categories() -> None:
    scenarios = get_standard_evaluation_scenarios()
    categories = {s.category.value for s in scenarios}
    assert len(scenarios) == 10
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


def test_independent_evaluator_runs_and_generates_report(tmp_path: Path) -> None:
    evaluator = IndependentEvaluator(output_dir=str(tmp_path))
    scenarios = get_standard_evaluation_scenarios()
    report = evaluator.run_all(scenarios)

    assert report.total_scenarios == 10
    assert report.passed_scenarios == 10
    assert report.pass_rate == 1.0
    assert report.policy_adherence_rate == 1.0
    assert report.truthfulness_rate == 1.0

    report_json = tmp_path / "evaluation_report.json"
    assert report_json.exists()
    assert '"truthfulness_rate": 1.0' in report_json.read_text(encoding="utf-8")
