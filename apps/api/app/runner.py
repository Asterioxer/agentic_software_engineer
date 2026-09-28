from __future__ import annotations
from .domain import RunEvent,RunStatus,TaskSpec,ToolCall,VerificationResult
from .planner import plan_with_repository
from .policy import ToolPolicy
from .tools import ToolRegistry
class AgentRun:
    def __init__(self,task:TaskSpec,registry:ToolRegistry,policy:ToolPolicy)->None:
        self.task,self.registry,self.policy=task,registry,policy;self.events:list[RunEvent]=[]
    def _emit(self,status:RunStatus,message:str)->None:self.events.append(RunEvent(sequence=len(self.events)+1,status=status,message=message))
    def execute(self)->dict[str,object]:
        self._emit(RunStatus.INTAKE,"Task accepted.")
        try: plan,repository=plan_with_repository(self.task)
        except ValueError as exc:
            self._emit(RunStatus.FAILED,f"Repository inspection failed: {exc}");return {"status":"failed","events":self.events}
        self._emit(RunStatus.PLANNING,f"Built context-aware plan with {len(plan)} steps.")
        self._emit(RunStatus.EXECUTING,"Executing declared tools.")
        for step in plan:
            if not step.tool:continue
            call=ToolCall(tool=step.tool,arguments={"repository":self.task.repository});decision=self.policy.authorize(call)
            if not decision.allowed:self._emit(RunStatus.FAILED,decision.reason);return {"status":"failed","plan":plan,"repository":repository,"events":self.events}
            self.registry.get(step.tool).handler(call.arguments)
        self._emit(RunStatus.VERIFYING,"Running independent deterministic checks.")
        results=[VerificationResult(check="plan_exists",passed=bool(plan),detail="Plan is non-empty."),VerificationResult(check="repository_context",passed=self.task.repository is None or repository is not None,detail="Repository context was inspected when requested."),VerificationResult(check="tool_allowlist",passed=all(s.tool is None or self.policy.authorize(ToolCall(tool=s.tool)).allowed for s in plan),detail="Declared tools are policy-approved.")]
        if not all(x.passed for x in results):self._emit(RunStatus.FAILED,"Verification failed.");return {"status":"failed","plan":plan,"repository":repository,"verification":results,"events":self.events}
        self._emit(RunStatus.REFLECTING,"Summarizing execution evidence.");self._emit(RunStatus.COMPLETED,"Run completed with verification evidence.")
        return {"status":"completed","plan":plan,"repository":repository,"verification":results,"events":self.events}
