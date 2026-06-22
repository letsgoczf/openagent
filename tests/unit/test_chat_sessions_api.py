from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import app


def test_put_chat_sessions_rejects_blank_id_without_deleting_existing(
    tmp_path,
    monkeypatch,
) -> None:
    db = tmp_path / "chat.db"
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(sqlite_path=db)),
    )
    client = TestClient(app)

    good = {
        "version": 1,
        "activeSessionId": "s_1",
        "sessions": [
            {
                "id": "s_1",
                "title": "kept",
                "updatedAt": 1,
                "messages": [{"id": "m1", "role": "user", "content": "keep"}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    }
    assert client.put("/v1/chat-sessions/state", json=good).status_code == 200

    bad = {
        "version": 1,
        "activeSessionId": "",
        "sessions": [
            {
                "id": "   ",
                "title": "bad",
                "updatedAt": 2,
                "messages": [],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    }
    r = client.put("/v1/chat-sessions/state", json=bad)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "chat_sessions.bad_id"

    state = client.get("/v1/chat-sessions/state").json()
    assert state["activeSessionId"] == "s_1"
    assert [s["id"] for s in state["sessions"]] == ["s_1"]
    assert state["sessions"][0]["messages"][0]["content"] == "keep"


def test_put_chat_sessions_rejects_duplicate_trimmed_ids(tmp_path, monkeypatch) -> None:
    db = tmp_path / "chat.db"
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: SimpleNamespace(storage=SimpleNamespace(sqlite_path=db)),
    )
    client = TestClient(app)

    r = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "activeSessionId": "s_1",
            "sessions": [
                {
                    "id": "s_1",
                    "title": "one",
                    "updatedAt": 1,
                    "messages": [],
                    "lastEvidenceEntries": [],
                    "lastCitations": [],
                },
                {
                    "id": " s_1 ",
                    "title": "duplicate",
                    "updatedAt": 2,
                    "messages": [],
                    "lastEvidenceEntries": [],
                    "lastCitations": [],
                },
            ],
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "chat_sessions.duplicate_id"
