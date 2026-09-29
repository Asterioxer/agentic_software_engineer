from app.llm import build_advisor
from app.providers import DeterministicProvider

def test_advisor_falls_back_without_model_configuration(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    provider, name = build_advisor()
    assert isinstance(provider, DeterministicProvider)
    assert name == "deterministic"
