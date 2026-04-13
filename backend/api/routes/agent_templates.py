"""Agent 提示词模板目录（供前端 @ 补全）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.config_loader import load_config
from backend.prompts.catalog import discover_agent_templates

router = APIRouter(prefix="/v1", tags=["agent-templates"])


@router.get("/agent-templates")
async def list_agent_templates() -> dict[str, Any]:
    cfg = load_config()
    entries = discover_agent_templates(settings=cfg)
    return {
        "agents": [{"id": e.id, "blurb": e.blurb} for e in entries],
    }
