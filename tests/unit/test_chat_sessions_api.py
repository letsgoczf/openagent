from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.api.errors import ApiException
from backend.api.routes import chat_sessions


def _body(*, base_revision: int | None, session_id: str = "s_1"):
    return chat_sessions.PutChatSessionsStateDTO(
        version=1,
        baseRevision=base_revision,
        activeSessionId=session_id,
        sessions=[
            chat_sessions.ChatSessionPersistedDTO(
                id=session_id,
                title="test",
                updatedAt=1,
                messages=[],
            )
        ],
    )


def test_chat_sessions_put_requires_base_revision() -> None:
    with pytest.raises(ApiException) as exc_info:
        asyncio.run(chat_sessions.put_chat_sessions_state(_body(base_revision=None)))
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "chat_sessions.base_revision_required"


def test_chat_sessions_put_rejects_stale_revision(monkeypatch, tmp_path) -> None:
    config = SimpleNamespace(
        storage=SimpleNamespace(sqlite_path=str(tmp_path / "chat-sessions.db"))
    )
    monkeypatch.setattr(chat_sessions, "load_config", lambda: config)

    result = asyncio.run(
        chat_sessions.put_chat_sessions_state(_body(base_revision=0))
    )
    assert result.stateRevision == 1

    with pytest.raises(ApiException) as exc_info:
        asyncio.run(chat_sessions.put_chat_sessions_state(_body(base_revision=0)))
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "chat_sessions.conflict"
    assert exc_info.value.detail == {"currentRevision": 1}

    state = asyncio.run(chat_sessions.get_chat_sessions_state())
    assert state.stateRevision == 1
    assert [session.id for session in state.sessions] == ["s_1"]


def test_chat_sessions_put_rejects_blank_session_id() -> None:
    with pytest.raises(ApiException) as exc_info:
        asyncio.run(
            chat_sessions.put_chat_sessions_state(
                _body(base_revision=0, session_id="   ")
            )
        )
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "chat_sessions.blank_id"
