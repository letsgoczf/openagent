from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import app


def test_chat_sessions_api_rejects_stale_put(monkeypatch, tmp_path) -> None:
    db_path = tmp_path / "chat_sessions.db"
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(sqlite_path=str(db_path))),
    )
    client = TestClient(app)

    initial = client.get("/v1/chat-sessions/state")
    assert initial.status_code == 200
    assert initial.json()["stateRevision"] == 0

    first = client.put(
        "/v1/chat-sessions/state",
        json={
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
        },
    )
    assert first.status_code == 200
    assert first.json()["stateRevision"] == 1

    stale = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "activeSessionId": "s_2",
            "baseRevision": 0,
            "sessions": [
                {
                    "id": "s_2",
                    "title": "stale",
                    "updatedAt": 2,
                    "messages": [{"id": "m2", "role": "user", "content": "drop"}],
                    "lastEvidenceEntries": [],
                    "lastCitations": [],
                }
            ],
        },
    )
    assert stale.status_code == 409

    current = client.get("/v1/chat-sessions/state")
    assert current.status_code == 200
    body = current.json()
    assert body["stateRevision"] == 1
    assert body["activeSessionId"] == "s_1"
    assert [s["id"] for s in body["sessions"]] == ["s_1"]
    assert body["sessions"][0]["messages"][0]["content"] == "keep"
