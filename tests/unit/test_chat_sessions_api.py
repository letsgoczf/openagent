from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.api.routes import chat_sessions
from backend.config_loader import (
    GenerationConfig,
    ModelsConfig,
    OpenAgentSettings,
    StorageConfig,
)


def _settings(tmp_path) -> OpenAgentSettings:
    return OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="tiny",
                base_url="http://127.0.0.1:11434",
            )
        ),
        storage=StorageConfig(sqlite_path=str(tmp_path / "chat_sessions.db")),
    )


def _session(session_id: str, title: str, content: str) -> dict:
    return {
        "id": session_id,
        "title": title,
        "updatedAt": 100,
        "messages": [{"id": f"m_{session_id}", "role": "user", "content": content}],
        "lastEvidenceEntries": [],
        "lastCitations": [],
    }


def test_chat_sessions_api_rejects_stale_full_state_save(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(chat_sessions, "load_config", lambda: _settings(tmp_path))
    client = TestClient(app)

    initial = client.get("/v1/chat-sessions/state")
    assert initial.status_code == 200
    assert initial.json()["stateRevision"] == 0

    created = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "activeSessionId": "s_1",
            "baseRevision": 0,
            "sessions": [_session("s_1", "first", "keep")],
        },
    )
    assert created.status_code == 200
    assert created.json()["stateRevision"] == 1

    missing_base = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "activeSessionId": "s_2",
            "sessions": [_session("s_2", "missing", "bad")],
        },
    )
    assert missing_base.status_code == 400
    assert missing_base.json()["error"]["code"] == "chat_sessions.missing_base_revision"

    stale = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "activeSessionId": "s_2",
            "baseRevision": 0,
            "sessions": [_session("s_2", "stale", "drop")],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["detail"]["currentRevision"] == 1

    current = client.get("/v1/chat-sessions/state")
    assert current.status_code == 200
    data = current.json()
    assert data["stateRevision"] == 1
    assert data["activeSessionId"] == "s_1"
    assert [s["id"] for s in data["sessions"]] == ["s_1"]
    assert data["sessions"][0]["messages"][0]["content"] == "keep"
