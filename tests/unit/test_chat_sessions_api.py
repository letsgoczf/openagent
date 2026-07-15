from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api.app import app


def _session(session_id: str, updated_at: int) -> dict:
    return {
        "id": session_id,
        "title": session_id,
        "updatedAt": updated_at,
        "messages": [],
        "lastEvidenceEntries": [],
        "lastCitations": [],
    }


def test_stale_chat_sessions_put_returns_conflict_without_overwriting(tmp_path) -> None:
    settings = SimpleNamespace(
        storage=SimpleNamespace(sqlite_path=str(tmp_path / "chat-sessions.db"))
    )
    with (
        patch("backend.api.routes.chat_sessions.load_config", return_value=settings),
        TestClient(app) as client,
    ):
        initial = client.get("/v1/chat-sessions/state")
        assert initial.status_code == 200
        assert initial.json()["stateRevision"] == 0

        first = client.put(
            "/v1/chat-sessions/state",
            json={
                "version": 1,
                "activeSessionId": "first",
                "sessions": [_session("first", 2)],
                "baseRevision": 0,
            },
        )
        assert first.status_code == 200
        assert first.json()["stateRevision"] == 1

        stale = client.put(
            "/v1/chat-sessions/state",
            json={
                "version": 1,
                "activeSessionId": "stale",
                "sessions": [_session("stale", 1)],
                "baseRevision": 0,
            },
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "chat_sessions.conflict"
        assert stale.json()["error"]["detail"]["currentRevision"] == 1

        persisted = client.get("/v1/chat-sessions/state").json()
        assert persisted["stateRevision"] == 1
        assert [session["id"] for session in persisted["sessions"]] == ["first"]
