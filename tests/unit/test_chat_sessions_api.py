from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.api.app import app


def _cfg_for(path):
    return SimpleNamespace(storage=SimpleNamespace(sqlite_path=str(path)))


def test_chat_sessions_cors_rejects_untrusted_origin() -> None:
    client = TestClient(app)

    response = client.options(
        "/v1/chat-sessions/state",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") is None


def test_chat_sessions_cors_allows_local_frontend() -> None:
    client = TestClient(app)

    response = client.options(
        "/v1/chat-sessions/state",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_chat_sessions_put_rejects_missing_base_revision(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "chat.db"
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: _cfg_for(db_path),
    )
    client = TestClient(app)

    response = client.put(
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
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "chat_sessions.missing_base_revision"


def test_chat_sessions_stale_put_does_not_overwrite_state(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "chat.db"
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: _cfg_for(db_path),
    )
    client = TestClient(app)

    initial = client.get("/v1/chat-sessions/state").json()
    assert initial["stateRevision"] == 0

    first = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "baseRevision": initial["stateRevision"],
            "activeSessionId": "s_1",
            "sessions": [
                {
                    "id": "s_1",
                    "title": "one",
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
            "baseRevision": initial["stateRevision"],
            "activeSessionId": "s_2",
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
    assert stale.json()["error"]["code"] == "chat_sessions.conflict"

    current = client.get("/v1/chat-sessions/state").json()
    assert current["stateRevision"] == 1
    assert [s["id"] for s in current["sessions"]] == ["s_1"]
    assert current["sessions"][0]["messages"][0]["content"] == "keep"


def test_chat_sessions_rejects_trimmed_duplicate_ids(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "chat.db"
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: _cfg_for(db_path),
    )
    client = TestClient(app)

    response = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "baseRevision": 0,
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
                    "title": "dupe",
                    "updatedAt": 2,
                    "messages": [],
                    "lastEvidenceEntries": [],
                    "lastCitations": [],
                },
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "chat_sessions.duplicate_id"
