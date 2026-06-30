from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.api.app import app
from backend.api.origin_policy import is_origin_allowed


def test_origin_policy_rejects_unknown_web_origin() -> None:
    assert is_origin_allowed("http://localhost:3000")
    assert not is_origin_allowed("https://evil.example")


def test_cors_preflight_rejects_cross_origin() -> None:
    client = TestClient(app)

    res = client.options(
        "/v1/chat-sessions/state",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


def test_websocket_rejects_cross_origin() -> None:
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws",
            headers={"origin": "https://evil.example"},
        ):
            pass
