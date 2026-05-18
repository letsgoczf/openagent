from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import app
import backend.api.routes.chat_sessions as chat_sessions_route


def test_chat_sessions_rejects_blank_id_without_deleting_existing(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "chat.db"
    monkeypatch.setattr(
        chat_sessions_route,
        "load_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(sqlite_path=db_path)),
    )
    client = TestClient(app)

    good = {
        "version": 1,
        "activeSessionId": "s_1",
        "sessions": [
            {
                "id": "s_1",
                "title": "keep",
                "updatedAt": 42,
                "messages": [{"id": "m1", "role": "user", "content": "keep me"}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    }
    assert client.put("/v1/chat-sessions/state", json=good).status_code == 200

    bad = {
        "version": 1,
        "activeSessionId": "   ",
        "sessions": [
            {
                "id": "   ",
                "title": "bad",
                "updatedAt": 43,
                "messages": [],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    }
    r = client.put("/v1/chat-sessions/state", json=bad)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "chat_sessions.bad_id"

    r = client.get("/v1/chat-sessions/state")
    assert r.status_code == 200
    data = r.json()
    assert data["activeSessionId"] == "s_1"
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["id"] == "s_1"
    assert data["sessions"][0]["messages"][0]["content"] == "keep me"
