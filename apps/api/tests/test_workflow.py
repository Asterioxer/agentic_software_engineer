from app.workflow import GitHubWorkflowPolicy, GitHubWorkflowRequest, WorkflowAction

def test_merge_requires_green() -> None:
    allowed, reason = GitHubWorkflowPolicy().authorize(
        GitHubWorkflowRequest(action=WorkflowAction.MERGE_PR, branch="feature"),
        checks_green=False,
    )
    assert not allowed
    assert "green" in reason
