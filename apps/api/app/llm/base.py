from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelUsage:
    """Token consumption and financial cost metrics for an LLM invocation."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_estimate_usd: float = 0.0
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ModelResponse:
    """Normalized response from an LLM provider."""

    content: str
    usage: ModelUsage
    model: str
    finish_reason: str = "stop"


@dataclass
class TokenBudget:
    """Guards against runaway LLM token consumption in autonomous task loops."""

    max_tokens: int = 100_000
    consumed_tokens: int = 0
    total_cost_usd: float = 0.0

    def record_usage(self, usage: ModelUsage) -> None:
        self.consumed_tokens += usage.total_tokens
        self.total_cost_usd += usage.cost_estimate_usd

    def is_exceeded(self) -> bool:
        return self.consumed_tokens >= self.max_tokens

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.consumed_tokens)


class ModelClient(ABC):
    """Abstract interface for LLM providers supporting synchronous and streaming token generation."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        """Generate complete response synchronously."""
        ...

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """Generate response asynchronously yielding string tokens."""
        ...
