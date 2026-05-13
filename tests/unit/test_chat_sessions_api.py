from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import app
from backend.api.routes import chat_sessions as chat_sessions_route
from backend.config_loader import load_config
from backend.storage.sqlite_store import SQLiteStore


def test_put_chat_sessions_state_rejects_blank_id_before_replace(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "chat-state.db"
    cfg = load_config()
    cfg = cfg.model_copy(
        update={"storage": cfg.storage.model_copy(update={"sqlite_path": str(db_path)})}
    )
    monkeypatch.setattr(chat_sessions_route, "load_config", lambda: cfg)

    store = SQLiteStore(db_path)
    store.put_ui_chat_state(
        active_session_id="s_keep",
        sessions=[
            {
                "id": "s_keep",
                "title": "keep",
                "updatedAt": 1,
                "messages": [{"id": "m1", "role": "user", "content": "saved"}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    )
    store.close()

    client = TestClient(app)
    response = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "activeSessionId": " ",
            "sessions": [
                {
                    "id": " ",
                    "title": "bad",
                    "updatedAt": 2,
                    "messages": [],
                    "lastEvidenceEntries": [],
                    "lastCitations": [],
                }
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "chat_sessions.bad_id"

    store = SQLiteStore(db_path)
    active, rows = store.get_ui_chat_state()
    store.close()
    assert active == "s_keep"
    assert len(rows) == 1
    assert rows[0]["messages"][0]["content"] == "saved"
