from app.change_analysis import analyze_diff

def test_change_analysis_classifies_sensitive_files() -> None:
    diff = "+++ b/infra/main.tf\n+resource\n+++ b/app.py\n+print(1)\n"
    result = analyze_diff(diff)
    assert result.risk == "high"
    assert result.files[0].risk == "high"
