from pathlib import Path
from app.verification_pipeline import run_verification

def test_verification_pipeline_returns_structured_evidence(tmp_path: Path) -> None:
    evidence = run_verification(str(tmp_path))
    assert evidence.checks
    assert any(item.check == "command:git.diff.check" for item in evidence.checks)
