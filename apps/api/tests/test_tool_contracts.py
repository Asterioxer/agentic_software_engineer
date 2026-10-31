from pathlib import Path

import pytest

from app.tools import build_default_registry


def test_tool_registry_rejects_extra_forbidden_fields() -> None:
    registry = build_default_registry()

    # workspace.plan with injected unknown field
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        registry.execute_guarded(
            "workspace.plan",
            {
                "kind": "write",
                "path": "test.txt",
                "content": "hello",
                "malicious_injected_field": True,
            },
        )


def test_tool_registry_rejects_invalid_action_kind() -> None:
    registry = build_default_registry()

    with pytest.raises(ValueError, match="Input should be 'write' or 'delete'"):
        registry.execute_guarded(
            "workspace.plan",
            {
                "kind": "format_disk",
                "path": "test.txt",
            },
        )


def test_tool_registry_rejects_unallowlisted_command() -> None:
    registry = build_default_registry()

    with pytest.raises(ValueError, match="Input should be 'python.tests'"):
        registry.execute_guarded(
            "command.run",
            {
                "command_id": "rm -rf /",
            },
        )


def test_tool_registry_rejects_invalid_timeout_bounds() -> None:
    registry = build_default_registry()

    # Negative timeout
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        registry.execute_guarded(
            "command.run",
            {
                "command_id": "git.diff.check",
                "timeout_seconds": -5.0,
            },
        )

    # Exceeding max timeout
    with pytest.raises(ValueError, match="less than or equal to 60"):
        registry.execute_guarded(
            "command.run",
            {
                "command_id": "git.diff.check",
                "timeout_seconds": 120.0,
            },
        )


def test_tool_registry_valid_calls_succeed(tmp_path: Path) -> None:
    registry = build_default_registry()

    res, rec = registry.execute_guarded(
        "repository.inspect",
        {
            "repository": str(tmp_path),
            "query": "main",
            "max_files": 100,
        },
    )
    assert res["inspected"] is True
    assert rec.passed is True
