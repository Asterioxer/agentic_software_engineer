from __future__ import annotations

import argparse
from pathlib import Path

from app.cli import (
    build_parser,
    cmd_inspect,
    cmd_resume,
    cmd_review,
    cmd_run,
    cmd_status,
    format_table,
    main,
)
from app.domain import RunStatus, TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun
from app.store import RunStore
from app.tools import build_default_registry


def test_format_table() -> None:
    headers = ["Col A", "Col B"]
    rows = [["val1", "val2"], ["longervalue", "short"]]
    table = format_table(headers, rows)
    assert "Col A" in table
    assert "Col B" in table
    assert "longervalue" in table
    assert "-+-" in table


def test_cli_parser_help() -> None:
    parser = build_parser()
    assert parser.prog == "agentic-engineer"


def test_cli_run_dry_run(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test_cli.db")
    args = argparse.Namespace(
        title="Check system health",
        desc="Safe read-only execution",
        repo=str(tmp_path),
        no_dry_run=False,
        auto_approve=False,
        db=db_path,
    )
    code = cmd_run(args)
    assert code == 0


def test_cli_run_mutation_awaiting_approval(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test_cli_mut.db")
    args = argparse.Namespace(
        title="Fix database bug",
        desc="Requires mutating workspace files",
        repo=str(tmp_path),
        no_dry_run=True,
        auto_approve=False,
        db=db_path,
    )
    code = cmd_run(args)
    # High-risk mutation without auto-approve should await approval (exit code 2)
    assert code == 2


def test_cli_status_and_resume(tmp_path: Path) -> None:
    db_path = str(tmp_path / "test_cli_sr.db")
    store = RunStore(db_path)
    registry = build_default_registry()
    policy = ToolPolicy()

    task = TaskSpec(
        title="Refactor auth",
        description="Refactor authentication system",
        repository=str(tmp_path),
        dry_run=False,
        auto_approve=False,
    )
    run = AgentRun(task, registry, policy, store=store)
    result = run.execute()
    assert result["status"] == RunStatus.AWAITING_APPROVAL.value

    # Check status via CLI
    status_args = argparse.Namespace(run_id=run.run_id, db=db_path)
    status_code = cmd_status(status_args)
    assert status_code == 0

    # Resume with approval via CLI
    resume_args = argparse.Namespace(run_id=run.run_id, approve=True, db=db_path)
    resume_code = cmd_resume(resume_args)
    assert resume_code == 0

    # Test status for non-existent run
    not_found_args = argparse.Namespace(run_id="non_existent_run_999", db=db_path)
    assert cmd_status(not_found_args) == 1


def test_cli_review_clean_and_vulnerable(tmp_path: Path) -> None:
    clean_file = tmp_path / "clean.py"
    clean_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    clean_args = argparse.Namespace(target=str(clean_file))
    assert cmd_review(clean_args) == 0

    vuln_file = tmp_path / "vuln.py"
    vuln_file.write_text("API_KEY = 'AKIA1111111111111111'\n", encoding="utf-8")
    vuln_args = argparse.Namespace(target=str(vuln_file))
    assert cmd_review(vuln_args) == 1

    missing_args = argparse.Namespace(target=str(tmp_path / "does_not_exist.py"))
    assert cmd_review(missing_args) == 1


def test_cli_inspect(tmp_path: Path) -> None:
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text('{"dependencies": {"react": "^19.0.0"}}', encoding="utf-8")

    inspect_args = argparse.Namespace(repo=str(tmp_path))
    assert cmd_inspect(inspect_args) == 0


def test_cli_main_entrypoint(tmp_path: Path) -> None:
    clean_file = tmp_path / "safe.py"
    clean_file.write_text("x = 42\n", encoding="utf-8")

    code = main(["review", str(clean_file)])
    assert code == 0


def test_cli_export_dataset(tmp_path: Path) -> None:
    db_path = str(tmp_path / "export_test.db")
    store = RunStore(db_path)
    task = TaskSpec(title="Verified run", description="Testing export", repository=str(tmp_path))
    run = AgentRun(task, build_default_registry(), ToolPolicy(), store=store)
    run.execute()

    out_file = tmp_path / "exported.jsonl"
    code = main(["export-dataset", "--out", str(out_file), "--db", db_path])
    assert code == 0
    assert out_file.exists()


def test_cli_graph(tmp_path: Path) -> None:
    (tmp_path / "mod_a.py").write_text("def a(): pass\n", encoding="utf-8")
    (tmp_path / "mod_b.py").write_text("import mod_a\ndef b(): mod_a.a()\n", encoding="utf-8")

    # Full graph summary
    code = main(["graph", str(tmp_path)])
    assert code == 0

    # Blast radius on mod_a.py
    code = main(["graph", str(tmp_path), "--target", "mod_a.py"])
    assert code == 0
