from app.domain import TaskSpec
from app.planner import build_deterministic_plan

def test_repository_context_is_included_in_plan() -> None:
    task=TaskSpec(title="Improve search",description="Improve repository search.",repository="repo")
    plan=build_deterministic_plan(task,{"file_count":42})
    assert "42 indexed files" in plan[1].description

def test_repository_free_plan_skips_inspection() -> None:
    task=TaskSpec(title="Design API",description="Design an API.")
    plan=build_deterministic_plan(task)
    assert all(step.tool!="repository.inspect" for step in plan)
