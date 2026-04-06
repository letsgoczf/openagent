from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatStartRequest(BaseModel):
    type: Literal["chat.start"] = "chat.start"
    client_request_id: str = Field(default_factory=lambda: "req_" + uuid.uuid4().hex)
    query: str
    version_scope: list[str] | None = None
    stream: bool = True


class ChatDeltaMessage(BaseModel):
    type: Literal["chat.delta"] = "chat.delta"
    client_request_id: str
    run_id: str
    sequence: int
    delta_kind: Literal["thinking", "content", "citations"] | str = "content"
    delta: str


class ChatCompletedMessage(BaseModel):
    type: Literal["chat.completed"] = "chat.completed"
    client_request_id: str
    run_id: str
    sequence: int
    answer: str
    degraded: bool
    citations: list[dict[str, Any]] = []
    evidence_entries: list[dict[str, Any]] = []
    degrade_reason: str | None = None
    retrieval_state: dict[str, Any] = {}


class ApiErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    code: str
    message: str
    detail: dict[str, Any] = {}


class DocumentImportResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing"] = "queued"


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    progress: dict[str, Any] = {}
    error: str | None = None
    doc_id: str | None = None
    version_id: str | None = None


class TraceEvent(BaseModel):
    event_id: str
    sequence_num: int = Field(alias="sequence_num")
    event_type: str
    payload: dict[str, Any] | None = None
    created_at: str

