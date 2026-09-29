from pathlib import Path

from app.domain import TaskSpec
from app.policy import ToolPolicy
from app.runner import AgentRun
from app.tools import build_default_registry

def test_agent_run_returns_verification_evidence(tmp_path: Path) -> None:
    result = AgentRun(
        TaskSpec(title="Verify repository", description="Check the workspace", repository=str(tmp_path)),
        build_default_registry(),
        ToolPolicy(),
    ).execute()
    assert result["status"] == "completed"
    assert result["verification"]
    assert result["tool_results"]
