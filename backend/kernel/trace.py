from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from backend.storage.sqlite_store import SQLiteStore


class TraceWriter:
    """将结构化事件落入 SQLite ``trace_event``（供前端 / Eval 回放）。"""

    def __init__(
        self,
        store: SQLiteStore,
        run_id: str,
        *,
        on_emit: Callable[[str, str, dict[str, Any] | None, int, str], None] | None = None,
    ) -> None:
        self._store = store
        self._run_id = run_id
        self._seq = 0
        self._on_emit = on_emit

    @property
    def run_id(self) -> str:
        return self._run_id

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> str:
        self._seq += 1
        eid = str(uuid.uuid4())
        self._store.insert_trace_event(
            eid,
            self._run_id,
            self._seq,
            event_type,
            payload,
        )
        if self._on_emit is not None:
            self._on_emit(self._run_id, event_type, payload, self._seq, eid)
        return eid
