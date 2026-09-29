from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

from .providers import DeterministicProvider, PlanRequest, PlanningProvider

@dataclass(frozen=True)
class Advisory:
    provider: str
    text: str

class OllamaProvider:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def plan(self, request: PlanRequest) -> str:
        payload = json.dumps({
            "model": self.model,
            "prompt": (
                "You are an advisory software-engineering planner. "
                "Do not execute commands. Return a concise implementation strategy.\n"
                f"Task: {request.task}\nRepository: {request.repository_context}"
            ),
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            self.base_url + "/api/generate",
            data=payload,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode())
        return str(data.get("response", ""))

def build_advisor() -> tuple[PlanningProvider, str]:
    base_url = os.getenv("OLLAMA_BASE_URL")
    model = os.getenv("OLLAMA_MODEL")
    if base_url and model:
        return OllamaProvider(base_url, model), "ollama"
    return DeterministicProvider(), "deterministic"
