from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.domain import FailureCategory
from app.llm.repair import CodeRepairResult, ModelUsage
from app.self_correction import SelfCorrectionEngine


def test_failure_classification_categories() -> None:
    engine = SelfCorrectionEngine()

    assert (
        engine.classify_detailed_failure("SyntaxError: invalid syntax", "syntax:main.py")
        == FailureCategory.SYNTAX_ERROR
    )
    assert (
        engine.classify_detailed_failure("ModuleNotFoundError: No module named 'fastapi'")
        == FailureCategory.DEPENDENCY_MISSING
    )
    assert (
        engine.classify_detailed_failure("Command not allowlisted by execution policy")
        == FailureCategory.POLICY_VIOLATION
    )
    assert (
        engine.classify_detailed_failure("Approval fingerprint mismatch detected")
        == FailureCategory.APPROVAL_INVALIDATED
    )
    assert (
        engine.classify_detailed_failure("Strategy loop detected in repair attempts")
        == FailureCategory.STRATEGY_LOOP
    )
    assert (
        engine.classify_detailed_failure("Execution timed out after 30 seconds")
        == FailureCategory.TIMEOUT
    )
    assert (
        engine.classify_detailed_failure("AssertionError: assert 1 == 2", "test:test_core.py")
        == FailureCategory.VALIDATION_FAILURE
    )
    assert (
        engine.classify_detailed_failure("Run cancelled by operator") == FailureCategory.CANCELLED
    )


def test_failure_signature_deterministic() -> None:
    sig1 = SelfCorrectionEngine.compute_failure_signature(
        "syntax_error", "Invalid syntax", "main.py"
    )
    sig2 = SelfCorrectionEngine.compute_failure_signature(
        "syntax_error", "Invalid syntax", "main.py"
    )
    sig3 = SelfCorrectionEngine.compute_failure_signature(
        "syntax_error", "Different syntax", "main.py"
    )

    assert sig1 == sig2
    assert sig1 != sig3
    assert len(sig1) == 16


def test_anti_cycling_loop_detection() -> None:
    engine = SelfCorrectionEngine(max_strategy_repeats=1)
    sig = engine.compute_failure_signature("syntax_error", "Missing colon", "script.py")
    fix_code = "def foo():\n    return 42\n"

    # Initially not cycling
    assert not engine.is_cycling(sig, fix_code)

    # Record first attempt
    engine.record_attempt(sig, "syntax_error", "script.py", fix_code)

    # Second check for identical fix indicates loop
    assert engine.is_cycling(sig, fix_code)

    # Different fix does not loop
    different_fix = "def foo():\n    return 100\n"
    assert not engine.is_cycling(sig, different_fix)


def test_corrective_plan_detects_strategy_loop_on_repeated_failure(tmp_path: Path) -> None:
    engine = SelfCorrectionEngine(max_strategy_repeats=1)
    test_file = tmp_path / "broken.py"
    test_file.write_text("def broken_func(\n    pass\n", encoding="utf-8")

    # First attempt generates valid repair
    plan1 = engine.generate_corrective_plan(
        "syntax:broken.py", "SyntaxError: invalid syntax", tmp_path
    )
    assert plan1.approved is True
    assert not plan1.is_loop

    # Second attempt with same failure and same output triggers STRATEGY_LOOP
    plan2 = engine.generate_corrective_plan(
        "syntax:broken.py", "SyntaxError: invalid syntax", tmp_path
    )
    assert plan2.is_loop is True
    assert plan2.approved is False
    assert plan2.category == FailureCategory.STRATEGY_LOOP
    assert "strategy loop" in plan2.explanation.lower()


def test_corrective_plan_handles_missing_file(tmp_path: Path) -> None:
    engine = SelfCorrectionEngine()
    plan = engine.generate_corrective_plan("syntax:nonexistent.py", "SyntaxError", tmp_path)
    assert plan.approved is False
    assert plan.proposed_code is None
    assert "does not exist" in (plan.rejection_reason or "")


def test_corrective_plan_security_critic_gating(tmp_path: Path) -> None:
    engine = SelfCorrectionEngine()
    test_file = tmp_path / "app.py"
    test_file.write_text("def handler():\n    pass\n", encoding="utf-8")

    # Mock repair_code to return insecure code
    insecure_repair = CodeRepairResult(
        success=True,
        repaired_code='API_KEY = "sk_live_1234567890abcdef"\n',
        explanation="Added api key",
        syntax_valid=True,
        model_usage=ModelUsage(prompt_tokens=10, completion_tokens=10, total_tokens=20),
    )

    with patch("app.self_correction.repair_code", return_value=insecure_repair):
        plan = engine.generate_corrective_plan("syntax:app.py", "Fix auth", tmp_path)
        assert plan.approved is False
        assert "Security Critic" in (plan.rejection_reason or "")
