from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import app


def test_chat_sessions_state_rejects_stale_put(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "chat-sessions.db"
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(sqlite_path=str(db_path))),
    )
    client = TestClient(app)

    first = client.get("/v1/chat-sessions/state")
    assert first.status_code == 200
    assert first.json()["stateRevision"] == 0

    payload = {
        "version": 1,
        "activeSessionId": "s_1",
        "baseRevision": 0,
        "sessions": [
            {
                "id": "s_1",
                "title": "first",
                "updatedAt": 1,
                "messages": [{"id": "m1", "role": "user", "content": "keep"}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    }
    saved = client.put("/v1/chat-sessions/state", json=payload)
    assert saved.status_code == 200
    assert saved.json()["stateRevision"] == 1

    stale = {
        **payload,
        "activeSessionId": "s_2",
        "sessions": [
            {
                "id": "s_2",
                "title": "stale",
                "updatedAt": 2,
                "messages": [],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    }
    conflict = client.put("/v1/chat-sessions/state", json=stale)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "chat_sessions.revision_conflict"

    after = client.get("/v1/chat-sessions/state").json()
    assert after["activeSessionId"] == "s_1"
    assert after["stateRevision"] == 1
    assert after["sessions"][0]["messages"][0]["content"] == "keep"
