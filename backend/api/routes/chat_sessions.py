"""前端聊天会话 UI 状态：持久化到 SQLite，替代浏览器 localStorage。"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api.errors import ApiException
from backend.config_loader import load_config
from backend.storage.sqlite_store import SQLiteStore, UIChatStateConflictError

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


class ChatSessionsStateResponseDTO(ChatSessionsStateDTO):
    stateRevision: int = 0


class ChatSessionsStatePutDTO(ChatSessionsStateDTO):
    baseRevision: int | None = None


class ChatSessionsStatePutResponseDTO(BaseModel):
    ok: bool
    stateRevision: int


@router.get("/state", response_model=ChatSessionsStateResponseDTO)
async def get_chat_sessions_state() -> ChatSessionsStateResponseDTO:
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        active, rows, revision = sqlite.get_ui_chat_state()
        return ChatSessionsStateResponseDTO(
            version=1,
            activeSessionId=active,
            sessions=[ChatSessionPersistedDTO.model_validate(s) for s in rows],
            stateRevision=revision,
        )
    finally:
        sqlite.close()


@router.put("/state", response_model=ChatSessionsStatePutResponseDTO)
async def put_chat_sessions_state(
    body: ChatSessionsStatePutDTO,
) -> ChatSessionsStatePutResponseDTO:
    if body.baseRevision is None:
        raise ApiException(
            code="chat_sessions.missing_base_revision",
            message="baseRevision is required",
            status_code=400,
        )
    if not body.sessions:
        raise ApiException(
            code="chat_sessions.empty",
            message="sessions must not be empty",
            status_code=400,
        )
    ids: set[str] = set()
    for s in body.sessions:
        sid = s.id.strip()
        if not sid:
            raise ApiException(
                code="chat_sessions.blank_id",
                message="session id must not be blank",
                status_code=400,
            )
        ids.add(sid)
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
        rows = [s.model_dump(mode="json") for s in body.sessions]
        revision = sqlite.put_ui_chat_state(
            active_session_id=active,
            sessions=rows,
            base_revision=body.baseRevision,
        )
        return ChatSessionsStatePutResponseDTO(ok=True, stateRevision=revision)
    except UIChatStateConflictError as exc:
        raise ApiException(
            code="chat_sessions.revision_conflict",
            message="chat session state has changed; reload before saving",
            status_code=409,
            detail={"currentRevision": exc.actual_revision},
        ) from exc
    finally:
        sqlite.close()
