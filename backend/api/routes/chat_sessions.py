"""前端聊天会话 UI 状态：持久化到 SQLite，替代浏览器 localStorage。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api.errors import ApiException
from backend.config_loader import load_config
from backend.storage.sqlite_store import SQLiteStore

router = APIRouter(prefix="/v1/chat-sessions", tags=["chat-sessions"])


class ChatSessionPersistedDTO(BaseModel):
    id: str
    title: str = "新会话"
    updatedAt: int = 0
    messages: list[dict[str, Any]] = Field(default_factory=list)
    lastEvidenceEntries: list[dict[str, Any]] = Field(default_factory=list)
    lastCitations: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionsStateDTO(BaseModel):
    version: Literal[1] = 1
    activeSessionId: str | None = None
    sessions: list[ChatSessionPersistedDTO]


@router.get("/state", response_model=ChatSessionsStateDTO)
async def get_chat_sessions_state() -> ChatSessionsStateDTO:
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        active, rows = sqlite.get_ui_chat_state()
        return ChatSessionsStateDTO(
            version=1,
            activeSessionId=active,
            sessions=[ChatSessionPersistedDTO.model_validate(s) for s in rows],
        )
    finally:
        sqlite.close()


@router.put("/state", response_model=dict)
async def put_chat_sessions_state(body: ChatSessionsStateDTO) -> dict[str, bool]:
    if not body.sessions:
        raise ApiException(
            code="chat_sessions.empty",
            message="sessions must not be empty",
            status_code=400,
        )
    normalized_ids = [s.id.strip() for s in body.sessions]
    if any(not sid for sid in normalized_ids):
        raise ApiException(
            code="chat_sessions.bad_id",
            message="session id must not be empty",
            status_code=400,
        )
    ids = set(normalized_ids)
    if len(ids) != len(body.sessions):
        raise ApiException(
            code="chat_sessions.duplicate_id",
            message="duplicate session id",
            status_code=400,
        )
    active = body.activeSessionId.strip() if body.activeSessionId else None
    if active and active not in ids:
        raise ApiException(
            code="chat_sessions.bad_active",
            message="activeSessionId must refer to an existing session",
            status_code=400,
        )
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        rows = []
        for s, sid in zip(body.sessions, normalized_ids, strict=True):
            row = s.model_dump(mode="json")
            row["id"] = sid
            rows.append(row)
        sqlite.put_ui_chat_state(active_session_id=active, sessions=rows)
        return {"ok": True}
    finally:
        sqlite.close()
