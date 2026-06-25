"""前端聊天会话 UI 状态：持久化到 SQLite，替代浏览器 localStorage。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api.errors import ApiException
from backend.config_loader import load_config
from backend.storage.sqlite_store import SQLiteStore, UiChatStateConflict

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
    stateRevision: int = Field(default=0, ge=0)
    sessions: list[ChatSessionPersistedDTO]


class ChatSessionsSaveDTO(BaseModel):
    version: Literal[1] = 1
    activeSessionId: str | None = None
    baseRevision: int | None = Field(default=None, ge=0)
    sessions: list[ChatSessionPersistedDTO]


@router.get("/state", response_model=ChatSessionsStateDTO)
async def get_chat_sessions_state() -> ChatSessionsStateDTO:
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        active, rows, revision = sqlite.get_ui_chat_state()
        return ChatSessionsStateDTO(
            version=1,
            activeSessionId=active,
            stateRevision=revision,
            sessions=[ChatSessionPersistedDTO.model_validate(s) for s in rows],
        )
    finally:
        sqlite.close()


@router.put("/state", response_model=dict)
async def put_chat_sessions_state(body: ChatSessionsSaveDTO) -> dict[str, bool | int]:
    if body.baseRevision is None:
        raise ApiException(
            code="chat_sessions.missing_base_revision",
            message="baseRevision is required for full-state saves",
            status_code=400,
        )
    if not body.sessions:
        raise ApiException(
            code="chat_sessions.empty",
            message="sessions must not be empty",
            status_code=400,
        )
    ids: set[str] = set()
    for session in body.sessions:
        sid = session.id.strip()
        if not sid or sid != session.id:
            raise ApiException(
                code="chat_sessions.bad_id",
                message="session id must not be blank or padded",
                status_code=400,
            )
        ids.add(sid)
    if len(ids) != len(body.sessions):
        raise ApiException(
            code="chat_sessions.duplicate_id",
            message="duplicate session id",
            status_code=400,
        )
    active = body.activeSessionId
    if active and active not in ids:
        raise ApiException(
            code="chat_sessions.bad_active",
            message="activeSessionId must refer to an existing session",
            status_code=400,
        )
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        rows = [s.model_dump(mode="json") for s in body.sessions]
        revision = sqlite.put_ui_chat_state(
            active_session_id=active,
            sessions=rows,
            expected_revision=body.baseRevision,
        )
        return {"ok": True, "stateRevision": revision}
    except UiChatStateConflict as exc:
        raise ApiException(
            code="chat_sessions.conflict",
            message="chat session state has changed; reload before saving",
            status_code=409,
            detail={"currentRevision": exc.current_revision},
        ) from exc
    finally:
        sqlite.close()
