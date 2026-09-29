from app.domain import VerificationResult
from app.reflection import reflect

def test_reflection_preserves_bounded_retry() -> None:
    result = reflect([VerificationResult(check="tests", passed=False, detail="failed")])
    assert result.retry_budget == 2
    assert not result.passed
