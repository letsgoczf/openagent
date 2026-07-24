"""UI chat session 全量替换不得因空白 id 清空全部会话。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.storage.sqlite_store import SQLiteStore


@pytest.fixture
def sqlite_db(tmp_path):
    path = tmp_path / "chat_sessions_unit.db"
    store = SQLiteStore(path)
    yield store
    store.close()


def test_put_ui_chat_state_rejects_blank_ids_without_wiping(sqlite_db: SQLiteStore) -> None:
    sqlite_db.put_ui_chat_state(
        active_session_id="keep",
        sessions=[
            {
                "id": "keep",
                "title": "safe",
                "updatedAt": 1,
                "messages": [{"id": "m1", "role": "user", "content": "hello"}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    )
    with pytest.raises(ValueError, match="blank"):
        sqlite_db.put_ui_chat_state(
            active_session_id=None,
            sessions=[
                {
                    "id": "   ",
                    "title": "wipe?",
                    "updatedAt": 2,
                    "messages": [],
                    "lastEvidenceEntries": [],
                    "lastCitations": [],
                }
            ],
        )
    active, rows = sqlite_db.get_ui_chat_state()
    assert active == "keep"
    assert len(rows) == 1
    assert rows[0]["id"] == "keep"
    assert rows[0]["messages"][0]["content"] == "hello"


def test_chat_sessions_api_rejects_whitespace_session_id(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "chat_sessions.db"
    store = SQLiteStore(db_path)
    store.put_ui_chat_state(
        active_session_id="s1",
        sessions=[
            {
                "id": "s1",
                "title": "ok",
                "updatedAt": 1,
                "messages": [{"id": "m1", "role": "user", "content": "keep me"}],
                "lastEvidenceEntries": [],
                "lastCitations": [],
            }
        ],
    )
    store.close()

    from backend.config_loader import load_config

    cfg = load_config()
    monkeypatch.setattr(cfg.storage, "sqlite_path", str(db_path))
    monkeypatch.setattr("backend.api.routes.chat_sessions.load_config", lambda: cfg)

    client = TestClient(app)
    r = client.put(
        "/v1/chat-sessions/state",
        json={
            "version": 1,
            "activeSessionId": None,
            "sessions": [{"id": "  ", "title": "bad", "updatedAt": 2, "messages": []}],
        },
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "chat_sessions.blank_id"

    # 确认未清空既有会话
    store2 = SQLiteStore(db_path)
    try:
        active, rows = store2.get_ui_chat_state()
        assert active == "s1"
        assert len(rows) == 1
        assert rows[0]["messages"][0]["content"] == "keep me"
    finally:
        store2.close()
