from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(str, Enum):
    INTAKE = "intake"
    PLANNING = "planning"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    repository: str | None = Field(default=None, max_length=500)
    constraints: list[str] = Field(default_factory=list, max_length=30)


class PlanStep(BaseModel):
    id: str
    description: str
    tool: str | None = None
    success_criteria: list[str] = Field(default_factory=list)


class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    check: str
    passed: bool
    detail: str


class RunEvent(BaseModel):
    sequence: int
    status: RunStatus
    message: str
