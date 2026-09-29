from app.security import allowed_origins

def test_allowed_origins_defaults_to_local_web(monkeypatch) -> None:
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert allowed_origins() == ["http://localhost:3000"]
