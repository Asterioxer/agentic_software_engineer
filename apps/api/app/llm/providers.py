from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from collections.abc import AsyncGenerator
from typing import Any

from .base import ModelClient, ModelResponse, ModelUsage

logger = logging.getLogger("agent.llm.providers")


class DeterministicModelClient(ModelClient):
    """Offline, deterministic model provider for reproducible testing and CI execution."""

    def __init__(self, model_name: str = "deterministic-v2") -> None:
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "deterministic"

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        start_time = time.perf_counter()
        # Analyze prompt intent
        if "repair" in prompt.lower() or "fix" in prompt.lower():
            content = (
                "# Deterministic Repair Proposal\n"
                "def resolve_issue():\n"
                '    """Automated fix resolving diagnosed syntax or validation error."""\n'
                "    return True\n"
            )
        elif "plan" in prompt.lower():
            content = (
                "Deterministic Strategy:\n"
                "1. Inspect repository structure and symbol definitions.\n"
                "2. Formulate minimal bounded unified diff.\n"
                "3. Apply security critic check (SEC-001..SEC-004).\n"
                "4. Execute independent verification gates."
            )
        else:
            content = f"Deterministic response for: {prompt[:80]}"

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(content) // 4)
        usage = ModelUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_estimate_usd=0.0,
            duration_ms=duration_ms,
        )
        return ModelResponse(content=content, usage=usage, model=self._model_name)

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        response = self.generate(prompt, system_instruction, temperature, max_tokens)
        words = response.content.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == 0 else " " + word
            yield chunk
            await asyncio.sleep(0.005)


class OpenAICompatibleClient(ModelClient):
    """Client for OpenAI, DeepSeek, and local inference engines (vLLM, Ollama, LM Studio)."""

    def __init__(
        self,
        api_key: str = "sk-placeholder",
        base_url: str = "https://api.openai.com/v1",
        model_name: str = "gpt-4o-mini",
        cost_per_m_in: float = 0.15,
        cost_per_m_out: float = 0.60,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._model_name = model_name
        self.cost_per_m_in = cost_per_m_in
        self.cost_per_m_out = cost_per_m_out

    @property
    def provider_name(self) -> str:
        return "openai_compatible"

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        start_time = time.perf_counter()
        messages: list[dict[str, str]] = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = json.dumps(
            {
                "model": self._model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        choice = data.get("choices", [{}])[0]
        content = choice.get("message", {}).get("content", "")
        raw_usage = data.get("usage", {})
        p_tokens = raw_usage.get("prompt_tokens", len(prompt) // 4)
        c_tokens = raw_usage.get("completion_tokens", len(content) // 4)
        total_t = raw_usage.get("total_tokens", p_tokens + c_tokens)

        cost = (p_tokens * self.cost_per_m_in + c_tokens * self.cost_per_m_out) / 1_000_000.0
        usage = ModelUsage(
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            total_tokens=total_t,
            cost_estimate_usd=cost,
            duration_ms=duration_ms,
        )
        return ModelResponse(
            content=content,
            usage=usage,
            model=self._model_name,
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        # Fallback to sync call executed in threadpool for non-streaming environments
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self.generate(prompt, system_instruction, temperature, max_tokens),
        )
        words = resp.content.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == 0 else " " + word
            yield chunk
            await asyncio.sleep(0.005)


class AnthropicClient(ModelClient):
    """Client for Anthropic Claude (Claude 3.5 Sonnet / Haiku)."""

    def __init__(
        self,
        api_key: str = "sk-ant-placeholder",
        model_name: str = "claude-3-5-sonnet-20241022",
    ) -> None:
        self.api_key = api_key
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> ModelResponse:
        start_time = time.perf_counter()
        payload_dict: dict[str, Any] = {
            "model": self._model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_instruction:
            payload_dict["system"] = system_instruction

        payload = json.dumps(payload_dict).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        content_blocks = data.get("content", [])
        text_content = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")

        raw_usage = data.get("usage", {})
        p_tokens = raw_usage.get("input_tokens", len(prompt) // 4)
        c_tokens = raw_usage.get("output_tokens", len(text_content) // 4)
        cost = (p_tokens * 3.0 + c_tokens * 15.0) / 1_000_000.0

        usage = ModelUsage(
            prompt_tokens=p_tokens,
            completion_tokens=c_tokens,
            total_tokens=p_tokens + c_tokens,
            cost_estimate_usd=cost,
            duration_ms=duration_ms,
        )
        return ModelResponse(
            content=text_content,
            usage=usage,
            model=self._model_name,
            finish_reason=data.get("stop_reason", "end_turn"),
        )

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self.generate(prompt, system_instruction, temperature, max_tokens),
        )
        words = resp.content.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == 0 else " " + word
            yield chunk
            await asyncio.sleep(0.005)
