from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .base import ModelClient, ModelResponse, ModelUsage
from .factory import get_model_client

logger = logging.getLogger("agent.llm.router")


class TaskComplexity(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


@dataclass
class RouterMetrics:
    total_routed: int = 0
    simple_routed: int = 0
    medium_routed: int = 0
    complex_routed: int = 0
    escalations: int = 0
    total_tokens_consumed: int = 0
    total_cost_usd: float = 0.0


class AdaptiveModelRouter:
    """Dynamically routes prompts to appropriate LLM tiers based on task complexity,

    cost constraints, and failure escalation.
    """

    def __init__(
        self,
        fast_tier: ModelClient | None = None,
        reasoning_tier: ModelClient | None = None,
    ) -> None:
        self.fast_tier = fast_tier or get_model_client(provider="ollama", model="qwen2.5-coder:7b")
        self.reasoning_tier = reasoning_tier or get_model_client()
        self.metrics = RouterMetrics()

    def classify_complexity(self, prompt: str, task_context: str | None = None) -> TaskComplexity:
        """Heuristically classify the cognitive complexity of the prompt."""
        combined = f"{task_context or ''}\n{prompt}".lower()

        # Complex architectural or high-risk markers
        complex_keywords = (
            "security",
            "vulnerability",
            "auth",
            "jwt",
            "encryption",
            "race condition",
            "deadlock",
            "migration",
            "architect",
            "blast radius",
            "concurrency",
            "deliberation",
        )
        if any(kw in combined for kw in complex_keywords):
            return TaskComplexity.COMPLEX

        # Multi-file context or long prompts imply complex reasoning
        file_matches = re.findall(r"\b[\w/-]+\.(?:py|ts|tsx|js|json|yaml|sql)\b", combined)
        if len(set(file_matches)) >= 3 or len(prompt) > 4000:
            return TaskComplexity.COMPLEX

        # Simple markers
        simple_keywords = (
            "typo",
            "docstring",
            "comment",
            "format",
            "lint",
            "syntax error",
            "rename variable",
            "license",
        )
        if any(kw in combined for kw in simple_keywords) and len(prompt) < 1500:
            return TaskComplexity.SIMPLE

        return TaskComplexity.MEDIUM

    def route_and_generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        task_context: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> tuple[ModelResponse, TaskComplexity]:
        """Classify complexity, dispatch to the optimal model tier, and handle escalation."""
        complexity = self.classify_complexity(prompt, task_context)
        self.metrics.total_routed += 1

        selected_client = (
            self.fast_tier if complexity == TaskComplexity.SIMPLE else self.reasoning_tier
        )
        if complexity == TaskComplexity.SIMPLE:
            self.metrics.simple_routed += 1
        elif complexity == TaskComplexity.MEDIUM:
            self.metrics.medium_routed += 1
        else:
            self.metrics.complex_routed += 1

        logger.info(
            "Routing request [complexity=%s] to %s (%s)",
            complexity.value,
            selected_client.provider_name,
            selected_client.model_name,
        )

        try:
            resp = selected_client.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self._record_usage(resp.usage)
            return resp, complexity
        except Exception as exc:
            # If fast tier failed, escalate to reasoning tier
            if selected_client is not self.reasoning_tier:
                logger.warning(
                    "Fast tier %s failed (%s); escalating to reasoning tier %s",
                    selected_client.model_name,
                    exc,
                    self.reasoning_tier.model_name,
                )
                self.metrics.escalations += 1
                resp = self.reasoning_tier.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._record_usage(resp.usage)
                return resp, TaskComplexity.COMPLEX
            raise

    def _record_usage(self, usage: ModelUsage) -> None:
        self.metrics.total_tokens_consumed += usage.total_tokens
        self.metrics.total_cost_usd += usage.cost_estimate_usd

    def get_metrics_summary(self) -> dict[str, Any]:
        return {
            "total_routed": self.metrics.total_routed,
            "simple_routed": self.metrics.simple_routed,
            "medium_routed": self.metrics.medium_routed,
            "complex_routed": self.metrics.complex_routed,
            "escalations": self.metrics.escalations,
            "total_tokens_consumed": self.metrics.total_tokens_consumed,
            "total_cost_usd": round(self.metrics.total_cost_usd, 4),
            "fast_tier_model": self.fast_tier.model_name,
            "reasoning_tier_model": self.reasoning_tier.model_name,
        }
