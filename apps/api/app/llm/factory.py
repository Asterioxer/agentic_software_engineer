from __future__ import annotations

import logging
import os

from .base import ModelClient
from .providers import (
    AnthropicClient,
    DeterministicModelClient,
    OpenAICompatibleClient,
)

logger = logging.getLogger("agent.llm.factory")


def get_model_client(
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ModelClient:
    """Resolve and instantiate the appropriate model client based on environment or explicit config."""
    prov = (provider or os.getenv("LLM_PROVIDER") or "").lower()

    if prov == "anthropic" or (not prov and os.getenv("ANTHROPIC_API_KEY")):
        key = api_key or os.getenv("ANTHROPIC_API_KEY") or ""
        m = model or os.getenv("ANTHROPIC_MODEL") or "claude-3-5-sonnet-20241022"
        logger.info("Using Anthropic model client: %s", m)
        return AnthropicClient(api_key=key, model_name=m)

    if prov == "openai" or (not prov and os.getenv("OPENAI_API_KEY")):
        key = api_key or os.getenv("OPENAI_API_KEY") or ""
        url = base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        m = model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        logger.info("Using OpenAI-compatible model client: %s at %s", m, url)
        return OpenAICompatibleClient(api_key=key, base_url=url, model_name=m)

    if prov == "ollama" or (not prov and os.getenv("OLLAMA_BASE_URL")):
        url = base_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
        m = model or os.getenv("OLLAMA_MODEL") or "qwen2.5-coder:7b"
        logger.info("Using local Ollama client: %s at %s", m, url)
        return OpenAICompatibleClient(
            api_key="ollama", base_url=f"{url.rstrip('/')}/v1", model_name=m
        )

    logger.debug("Using DeterministicModelClient for reproducible local execution.")
    return DeterministicModelClient(model_name=model or "deterministic-v2")
