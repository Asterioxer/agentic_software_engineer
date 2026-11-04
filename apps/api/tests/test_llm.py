from __future__ import annotations

import pytest

from app.llm import (
    AnthropicClient,
    DeterministicModelClient,
    ModelUsage,
    OpenAICompatibleClient,
    TokenBudget,
    build_advisor,
    get_model_client,
    repair_code,
)


def test_advisor_falls_back_without_model_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    _, name = build_advisor()
    assert name == "deterministic"


def test_token_budget_tracking() -> None:
    budget = TokenBudget(max_tokens=1000)
    assert not budget.is_exceeded()
    assert budget.remaining_tokens == 1000

    usage1 = ModelUsage(
        prompt_tokens=200, completion_tokens=300, total_tokens=500, cost_estimate_usd=0.005
    )
    budget.record_usage(usage1)
    assert budget.consumed_tokens == 500
    assert budget.remaining_tokens == 500
    assert budget.total_cost_usd == 0.005
    assert not budget.is_exceeded()

    usage2 = ModelUsage(
        prompt_tokens=300, completion_tokens=300, total_tokens=600, cost_estimate_usd=0.006
    )
    budget.record_usage(usage2)
    assert budget.consumed_tokens == 1100
    assert budget.is_exceeded()
    assert budget.remaining_tokens == 0


def test_deterministic_model_client_generate() -> None:
    client = DeterministicModelClient()
    assert client.provider_name == "deterministic"
    assert client.model_name == "deterministic-v2"

    resp = client.generate("Plan repository refactor")
    assert "Deterministic Strategy" in resp.content
    assert resp.usage.total_tokens > 0
    assert resp.usage.duration_ms >= 0.0


@pytest.mark.anyio
async def test_deterministic_model_client_stream() -> None:
    client = DeterministicModelClient()
    chunks: list[str] = []
    async for chunk in client.generate_stream("Please plan the feature"):
        chunks.append(chunk)

    full_text = "".join(chunks)
    assert "Deterministic Strategy" in full_text
    assert len(chunks) > 1


def test_code_repair_engine_success() -> None:
    broken_code = "def calculate_sum(a, b):\n    retur a + b\n"
    error = "SyntaxError: invalid syntax (line 2)"

    result = repair_code(
        broken_code=broken_code,
        error_message=error,
        test_output="SyntaxError: invalid syntax",
    )
    assert result.success
    assert result.syntax_valid
    assert "def " in result.repaired_code
    assert result.model_usage.total_tokens > 0


def test_model_client_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Default deterministic
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client_default = get_model_client()
    assert isinstance(client_default, DeterministicModelClient)

    # 2. OpenAI provider
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-12345")
    client_openai = get_model_client(provider="openai")
    assert isinstance(client_openai, OpenAICompatibleClient)
    assert client_openai.model_name == "gpt-4o-mini"

    # 3. Anthropic provider
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-12345")
    client_anthropic = get_model_client(provider="anthropic")
    assert isinstance(client_anthropic, AnthropicClient)
    assert "claude" in client_anthropic.model_name
