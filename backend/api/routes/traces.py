from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.config_loader import load_config
from backend.storage.sqlite_store import SQLiteStore


router = APIRouter(prefix="/v1", tags=["traces"])


@router.get("/traces/{run_id}", response_model=dict)
async def get_traces(run_id: str) -> dict[str, Any]:
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        events = sqlite.get_trace_events(run_id)
        return {"run_id": run_id, "events": events, "event_count": len(events)}
    finally:
        sqlite.close()

