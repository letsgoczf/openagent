from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.config_loader import load_config
from backend.storage.sqlite_store import SQLiteStore


router = APIRouter(prefix="/v1", tags=["jobs"])


def _latest_job_payload(sqlite: SQLiteStore, job_id: str) -> tuple[str, dict[str, Any] | None]:
    # job 状态事件类型
    event_types = ["job_completed", "job_failed", "job_progress", "job_started"]
    last = sqlite.get_last_trace_event(job_id, event_types=event_types)
    if not last:
        return "queued", None
    return last["event_type"], last["payload"]


@router.get("/jobs/{job_id}", response_model=dict)
async def get_job(job_id: str) -> dict[str, Any]:
    cfg = load_config()
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    try:
        event_type, payload = _latest_job_payload(sqlite, job_id)
        if event_type == "job_completed":
            return {
                "job_id": job_id,
                "status": "completed",
                "progress": {},
                "error": None,
                "doc_id": (payload or {}).get("doc_id"),
                "version_id": (payload or {}).get("version_id"),
            }
        if event_type == "job_failed":
            return {
                "job_id": job_id,
                "status": "failed",
                "progress": {},
                "error": (payload or {}).get("error") or "unknown error",
                "doc_id": None,
                "version_id": None,
            }
        if event_type == "job_progress":
            return {
                "job_id": job_id,
                "status": "processing",
                "progress": payload or {},
                "error": None,
                "doc_id": None,
                "version_id": None,
            }
        if event_type == "job_started":
            return {
                "job_id": job_id,
                "status": "processing",
                "progress": payload or {},
                "error": None,
                "doc_id": None,
                "version_id": None,
            }
        # queued
        return {
            "job_id": job_id,
            "status": "queued",
            "progress": {},
            "error": None,
            "doc_id": None,
            "version_id": None,
        }
    finally:
        sqlite.close()

