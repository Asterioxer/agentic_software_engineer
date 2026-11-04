from __future__ import annotations

from app.llm.base import ModelClient, ModelResponse
from app.llm.providers import DeterministicModelClient
from app.llm.router import AdaptiveModelRouter, TaskComplexity


class FailingMockClient(ModelClient):
    @property
    def provider_name(self) -> str:
        return "mock_fail"

    @property
    def model_name(self) -> str:
        return "mock_fail_model"

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        raise RuntimeError("Service unavailable 503")

    def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ):
        raise NotImplementedError


def test_router_classification_simple() -> None:
    router = AdaptiveModelRouter(
        fast_tier=DeterministicModelClient(model_name="fast-7b"),
        reasoning_tier=DeterministicModelClient(model_name="reasoning-pro"),
    )
    complexity = router.classify_complexity("Fix a typo in the docstring comment")
    assert complexity == TaskComplexity.SIMPLE


def test_router_classification_complex() -> None:
    router = AdaptiveModelRouter(
        fast_tier=DeterministicModelClient(model_name="fast-7b"),
        reasoning_tier=DeterministicModelClient(model_name="reasoning-pro"),
    )
    complexity = router.classify_complexity(
        "Refactor auth JWT token validation to eliminate potential race condition"
    )
    assert complexity == TaskComplexity.COMPLEX


def test_router_dispatch_and_metrics() -> None:
    fast = DeterministicModelClient(model_name="fast-7b")
    reasoning = DeterministicModelClient(model_name="reasoning-pro")
    router = AdaptiveModelRouter(fast_tier=fast, reasoning_tier=reasoning)

    # Route simple
    resp_s, comp_s = router.route_and_generate("Clean up format and lint comments")
    assert comp_s == TaskComplexity.SIMPLE
    assert resp_s.model == "fast-7b"

    # Route complex
    resp_c, comp_c = router.route_and_generate(
        "Fix security vulnerability in authentication tokens"
    )
    assert comp_c == TaskComplexity.COMPLEX
    assert resp_c.model == "reasoning-pro"

    metrics = router.get_metrics_summary()
    assert metrics["total_routed"] == 2
    assert metrics["simple_routed"] == 1
    assert metrics["complex_routed"] == 1
    assert metrics["escalations"] == 0


def test_router_escalation_on_fast_failure() -> None:
    failing_fast = FailingMockClient()
    reasoning = DeterministicModelClient(model_name="reasoning-pro")
    router = AdaptiveModelRouter(fast_tier=failing_fast, reasoning_tier=reasoning)

    # Simple task routes to fast tier first, fails, then escalates to reasoning
    resp, comp = router.route_and_generate("Fix docstring typo")
    assert resp.model == "reasoning-pro"
    assert comp == TaskComplexity.COMPLEX
    metrics = router.get_metrics_summary()
    assert metrics["escalations"] == 1
