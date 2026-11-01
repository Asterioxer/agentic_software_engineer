from pathlib import Path

from app.critic import review_code_snippet, review_diff, review_workspace


def test_critic_clean_code() -> None:
    code = """
def calculate_metrics(items: list[int]) -> int:
    return sum(items)
"""
    findings = review_code_snippet(code, "clean.py")
    assert len(findings) == 0


def test_critic_detects_hardcoded_secrets() -> None:
    code = """
AWS_TOKEN = "AKIA1234567890ABCDEF"
api_key = "sk_live_123456789abcdef"
"""
    findings = review_code_snippet(code, "secrets.py")
    assert len(findings) >= 2
    rule_ids = {f.rule_id for f in findings}
    assert "SEC-001" in rule_ids
    assert any(f.severity == "CRITICAL" for f in findings)


def test_critic_detects_insecure_execution() -> None:
    code = """
import os
import subprocess

def dangerous(user_input):
    eval(user_input)
    os.system("ls -la")
    subprocess.run(["ls"], shell=True)
"""
    findings = review_code_snippet(code, "exec.py")
    assert len(findings) >= 3
    rule_ids = {f.rule_id for f in findings}
    assert "SEC-002" in rule_ids


def test_critic_detects_sql_injection() -> None:
    code = """
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)
"""
    findings = review_code_snippet(code, "db.py")
    assert len(findings) >= 1
    assert any(f.rule_id == "SEC-003" for f in findings)


def test_critic_review_diff_rejection() -> None:
    bad_diff = """--- a/src/auth.py
+++ b/src/auth.py
@@ -1,2 +1,4 @@
 def login():
+    token = "secret_key_12345678"
+    eval("run_auth()")
     return True
"""
    review = review_diff(bad_diff)
    assert not review.approved
    assert review.risk_score >= 0.5
    assert len(review.findings) >= 2
    assert "Review rejected" in review.summary


def test_critic_review_diff_clean() -> None:
    clean_diff = """--- a/src/math.py
+++ b/src/math.py
@@ -1,2 +1,4 @@
 def add(a, b):
+    return a + b
"""
    review = review_diff(clean_diff)
    assert review.approved
    assert review.risk_score == 0.0
    assert len(review.findings) == 0


def test_critic_review_workspace(tmp_path: Path) -> None:
    safe_file = tmp_path / "safe.py"
    safe_file.write_text("x = 10\n", encoding="utf-8")
    unsafe_file = tmp_path / "unsafe.py"
    unsafe_file.write_text("eval('1+1')\n", encoding="utf-8")

    review = review_workspace(str(tmp_path), ["safe.py", "unsafe.py"])
    assert not review.approved
    assert any(f.file_path == "unsafe.py" for f in review.findings)
