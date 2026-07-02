from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.api.origin_policy import get_allowed_origins, is_allowed_origin


def test_default_allowed_origins_include_local_frontend_and_api() -> None:
    origins = get_allowed_origins()

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
    assert "http://localhost:8000" in origins
    assert is_allowed_origin(None)


def test_allowed_origins_env_override(monkeypatch) -> None:
    monkeypatch.setenv(
        "OPENAGENT_ALLOWED_ORIGINS",
        " https://app.example.test/ , http://localhost:5173 ",
    )

    assert get_allowed_origins() == [
        "https://app.example.test",
        "http://localhost:5173",
    ]
    assert is_allowed_origin("https://app.example.test")
    assert not is_allowed_origin("https://evil.example.test")


def test_cors_preflight_rejects_untrusted_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/v1/chat-sessions/state",
        headers={
            "Origin": "https://evil.example.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_preflight_allows_trusted_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/v1/chat-sessions/state",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
