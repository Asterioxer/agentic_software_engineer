from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from .execution import WorkspaceAction,WorkspaceExecutor
from .verification import verify_workspace
ToolHandler=Callable[[dict[str,Any]],dict[str,Any]]
@dataclass(frozen=True)
class ToolDefinition:
    name:str;description:str;handler:ToolHandler
class ToolRegistry:
    def __init__(self)->None:self._tools:dict[str,ToolDefinition]={}
    def register(self,d:ToolDefinition)->None:
        if d.name in self._tools:raise ValueError(f"Tool already registered: {d.name}")
        self._tools[d.name]=d
    def get(self,name:str)->ToolDefinition:return self._tools[name]
def build_default_registry()->ToolRegistry:
    r=ToolRegistry()
    r.register(ToolDefinition("repository.inspect","Bounded repository metadata",lambda a:{"repository":a.get("repository"),"inspected":True}))
    r.register(ToolDefinition("workspace.plan","Validate and execute bounded workspace actions",lambda a:WorkspaceExecutor(str(a.get("repository") or "."),dry_run=bool(a.get("dry_run",True))).apply(WorkspaceAction(kind=str(a.get("kind","write")),path=str(a.get("path","agent-plan.txt")),content=a.get("content"))).__dict__))
    r.register(ToolDefinition("verification.run","Verify expected workspace artifacts",lambda a:{"checks":[x.model_dump() for x in verify_workspace(str(a.get("repository") or "."),list(a.get("expected_files",[])))]}))
    return r
