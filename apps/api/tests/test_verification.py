from pathlib import Path

from app.verification import verify_proof_of_test, verify_syntax, verify_workspace


def test_verify_workspace(tmp_path: Path) -> None:
    (tmp_path / "result.txt").write_text("done", encoding="utf-8")
    results = verify_workspace(str(tmp_path), ["result.txt", "missing.txt"])
    # result.txt exists, missing.txt fails
    assert any(r.check == "file:result.txt" and r.passed for r in results)
    assert any(r.check == "file:missing.txt" and not r.passed for r in results)


def test_verify_syntax_python(tmp_path: Path) -> None:
    valid_py = tmp_path / "valid.py"
    valid_py.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    res_valid = verify_syntax(valid_py)
    assert res_valid is not None and res_valid.passed

    invalid_py = tmp_path / "invalid.py"
    invalid_py.write_text("def broken(:\n    pass\n", encoding="utf-8")
    res_invalid = verify_syntax(invalid_py)
    assert res_invalid is not None and not res_invalid.passed
    assert "Syntax error" in res_invalid.detail


def test_verify_syntax_json_and_toml(tmp_path: Path) -> None:
    valid_json = tmp_path / "config.json"
    valid_json.write_text('{"name": "test", "version": 1}', encoding="utf-8")
    assert verify_syntax(valid_json) is not None and verify_syntax(valid_json).passed  # type: ignore[union-attr]

    invalid_json = tmp_path / "bad.json"
    invalid_json.write_text("{broken json", encoding="utf-8")
    assert verify_syntax(invalid_json) is not None and not verify_syntax(invalid_json).passed  # type: ignore[union-attr]

    valid_toml = tmp_path / "config.toml"
    valid_toml.write_text('[project]\nname = "pkg"\n', encoding="utf-8")
    assert verify_syntax(valid_toml) is not None and verify_syntax(valid_toml).passed  # type: ignore[union-attr]


def test_verify_proof_of_test(tmp_path: Path) -> None:
    test_file = tmp_path / "test_calc.py"
    test_file.write_text("def test_addition():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    res_valid = verify_proof_of_test(test_file)
    assert res_valid is not None and res_valid.passed
    assert "1 verified test definition" in res_valid.detail

    empty_test = tmp_path / "test_empty.py"
    empty_test.write_text("# No tests here, only helper\ndef helper(): pass\n", encoding="utf-8")
    res_empty = verify_proof_of_test(empty_test)
    assert res_empty is not None and not res_empty.passed
    assert "contains no test definitions" in res_empty.detail


def test_verify_workspace_escapes_boundary(tmp_path: Path) -> None:
    results = verify_workspace(str(tmp_path), ["../../outside.txt"])
    assert len(results) == 1
    assert not results[0].passed
    assert "escapes the workspace root boundary" in results[0].detail
