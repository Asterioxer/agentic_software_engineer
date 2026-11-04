from __future__ import annotations

import hashlib
import hmac

from starlette.testclient import TestClient

from app.integrations import (
    format_github_pr_comment,
    parse_github_event,
    verify_github_signature,
)
from app.main import app

client = TestClient(app)


def test_verify_github_signature() -> None:
    secret = "my-webhook-secret-123"
    payload = b'{"action": "opened"}'
    valid_sig = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

    assert verify_github_signature(payload, valid_sig, secret)
    assert not verify_github_signature(payload, "sha256=invalid", secret)
    assert not verify_github_signature(payload, None, secret)
    # When no secret configured in dev mode, returns True
    assert verify_github_signature(payload, None, "")


def test_parse_github_event() -> None:
    # 1. Issues event
    issue_payload = {
        "action": "opened",
        "issue": {"number": 42, "title": "Fix auth crash", "body": "Token expired crashes handler"},
        "repository": {"full_name": "Asterioxer/repo"},
    }
    task = parse_github_event("issues", issue_payload)
    assert task is not None
    assert "Fix auth crash" in task.title
    assert "Token expired" in task.description

    # 2. Comment fix trigger
    comment_payload = {
        "action": "created",
        "issue": {"number": 105, "title": "Calculator divide by zero"},
        "comment": {"body": "@agentic-bot fix handle zero division properly"},
    }
    task_comment = parse_github_event("issue_comment", comment_payload)
    assert task_comment is not None
    assert "Fix #105" in task_comment.title

    # 3. Ignored event
    ignored = parse_github_event("star", {"action": "created"})
    assert ignored is None


def test_format_github_pr_comment() -> None:
    mock_result = {
        "status": "completed",
        "run_id": "run-test-999",
        "task": {"title": "Add multiplication feature"},
        "plan": [
            {
                "id": "step_1",
                "tool": "workspace.patch",
                "status": "completed",
                "description": "Apply math patch",
            }
        ],
        "verification": [{"check": "syntax:python", "passed": True, "detail": "Valid AST"}],
    }
    comment = format_github_pr_comment(mock_result)
    assert "SUCCESS" in comment
    assert "Add multiplication feature" in comment
    assert "`run-test-999`" in comment
    assert "`syntax:python`" in comment
    assert "PASS" in comment


def test_api_github_webhook_endpoint() -> None:
    payload = {
        "action": "opened",
        "issue": {"number": 7, "title": "Web safe check", "body": "Verify safe inspection"},
    }
    resp = client.post(
        "/api/v1/integrations/github/webhook",
        headers={"X-GitHub-Event": "issues"},
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["run_id"]
    assert "github_comment" in data
