from __future__ import annotations

from backend.api.origin_policy import allowed_origins, is_origin_allowed


def test_origin_policy_defaults_to_localhost(monkeypatch) -> None:
    monkeypatch.delenv("OPENAGENT_ALLOWED_ORIGINS", raising=False)

    origins = allowed_origins()

    assert "http://localhost:3000" in origins
    assert is_origin_allowed("http://localhost:3000")
    assert not is_origin_allowed("https://evil.example")


def test_origin_policy_env_override(monkeypatch) -> None:
    monkeypatch.setenv(
        "OPENAGENT_ALLOWED_ORIGINS",
        "https://app.example, http://127.0.0.1:3000/",
    )

    assert allowed_origins() == ["https://app.example", "http://127.0.0.1:3000"]
    assert is_origin_allowed("https://app.example")
    assert not is_origin_allowed("http://localhost:3000")
