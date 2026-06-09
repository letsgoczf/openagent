from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.config_loader import (
    EmbeddingConfig,
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
            ),
            embedding=EmbeddingConfig(
                provider="ollama",
                model_id="nomic-embed-text",
                base_url="http://127.0.0.1:11434",
                vector_dimensions=4,
            ),
        ),
        storage=StorageConfig(sqlite_path=str(tmp_path / "api.db")),
    )


def _state(session_id: str, *, base_revision: int) -> dict:
    return {
        "version": 1,
        "activeSessionId": session_id,
        "baseRevision": base_revision,
        "sessions": [
            {
                "id": session_id,
                "title": session_id,
                "updatedAt": base_revision + 1,
                "messages": [{"id": f"m_{session_id}", "role": "user", "content": session_id}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    }


def test_chat_sessions_state_rejects_stale_put(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: _settings(tmp_path),
    )
    client = TestClient(app)

    initial = client.get("/v1/chat-sessions/state")
    assert initial.status_code == 200
    base_revision = initial.json()["stateRevision"]

    first = client.put("/v1/chat-sessions/state", json=_state("s_new", base_revision=base_revision))
    assert first.status_code == 200
    assert first.json()["stateRevision"] == base_revision + 1

    stale = client.put("/v1/chat-sessions/state", json=_state("s_old", base_revision=base_revision))
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "chat_sessions.conflict"

    current = client.get("/v1/chat-sessions/state")
    assert current.status_code == 200
    body = current.json()
    assert body["activeSessionId"] == "s_new"
    assert [s["id"] for s in body["sessions"]] == ["s_new"]


def test_chat_sessions_state_requires_base_revision(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "backend.api.routes.chat_sessions.load_config",
        lambda: _settings(tmp_path),
    )
    client = TestClient(app)

    payload = _state("s_missing", base_revision=0)
    payload.pop("baseRevision")
    response = client.put("/v1/chat-sessions/state", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "chat_sessions.missing_base_revision"
