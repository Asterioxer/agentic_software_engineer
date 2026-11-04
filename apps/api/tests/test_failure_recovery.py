from app.domain import FailureCategory, VerificationResult
from app.reflection import classify_failure, reflect


def test_classify_failure_categories() -> None:
    # Policy violation
    d1 = classify_failure("Tool 'os.system' is not allowlisted.")
    assert d1.category == FailureCategory.POLICY_VIOLATION
    assert not d1.recoverable

    # Timeout
    d2 = classify_failure("Command subprocess timed out after 30 seconds.")
    assert d2.category == FailureCategory.TIMEOUT
    assert d2.recoverable

    # Syntax error
    d3 = classify_failure("SyntaxError: invalid syntax on line 12")
    assert d3.category == FailureCategory.SYNTAX_ERROR
    assert d3.recoverable

    # Missing dependency
    d4 = classify_failure("ModuleNotFoundError: No module named 'nonexistent_pkg'")
    assert d4.category == FailureCategory.DEPENDENCY_MISSING
    assert not d4.recoverable

    # Validation failure
    v_results = [VerificationResult(check="unit_tests", passed=False, detail="2 tests failed")]
    d5 = classify_failure("Validation failed", verification_results=v_results)
    assert d5.category == FailureCategory.VALIDATION_FAILURE
    assert d5.recoverable


def test_reflection_bounds_retry_budget() -> None:
    results = [
        VerificationResult(check="check1", passed=False, detail="Failed"),
        VerificationResult(check="check2", passed=True, detail="Passed"),
    ]
    ref = reflect(results, retry_budget=2)
    assert not ref.passed
    assert ref.retry_budget == 2
    assert "check1" in ref.diagnosis

    # When all pass
    all_passed = [VerificationResult(check="check1", passed=True, detail="Passed")]
    ref_pass = reflect(all_passed, retry_budget=2)
    assert ref_pass.passed
    assert ref_pass.retry_budget == 0


from pathlib import Path

from app.domain import TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun
from app.store import RunStore
from app.tools import build_default_registry


def test_autonomous_self_healing_repair(tmp_path: Path) -> None:
    test_file = tmp_path / "broken.py"
    test_file.write_text("def broken():\n    retur False\n", encoding="utf-8")

    task = TaskSpec(
        title="Self-healing test",
        description="Fix broken file",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=True,
        max_retries=2,
    )
    store = RunStore(str(tmp_path / "sh.db"))
    run = AgentRun(task, build_default_registry(), ToolPolicy(), store=store)

    failing_results = [
        VerificationResult(check="syntax:broken.py", passed=False, detail="invalid syntax")
    ]
    repaired = run._attempt_self_healing_repair(failing_results)
    assert repaired
    assert run.retry_count == 1
    fixed_content = test_file.read_text(encoding="utf-8")
    assert "def " in fixed_content
