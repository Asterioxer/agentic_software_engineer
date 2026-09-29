from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class PlanRequest:
    task: str
    repository_context: str

class PlanningProvider(Protocol):
    def plan(self, request: PlanRequest) -> str: ...

class DeterministicProvider:
    def plan(self, request: PlanRequest) -> str:
        return (
            "Deterministic fallback: inspect repository context, make the smallest "
            "bounded change, then verify independently."
        )

class ProviderRouter:
    def __init__(self, provider: PlanningProvider | None = None) -> None:
        self.provider = provider or DeterministicProvider()

    def plan(self, request: PlanRequest) -> str:
        return self.provider.plan(request)
