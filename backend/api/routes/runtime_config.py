"""只读运行时配置（供前端 Settings 展示；不含密钥）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.config_loader import load_config

router = APIRouter(prefix="/v1", tags=["config"])


@router.get("/runtime-config", response_model=dict)
async def get_runtime_config() -> dict[str, Any]:
    cfg = load_config()
    gen = cfg.models.generation
    emb = cfg.models.embedding
    return {
        "generation": {
            "provider": gen.provider,
            "model_id": gen.model_id,
            "base_url": gen.base_url,
            "think": gen.think,
        },
        "embedding": {
            "provider": emb.provider,
            "model_id": emb.model_id,
            "base_url": emb.base_url,
            "vector_dimensions": emb.vector_dimensions,
        },
        "qdrant_collection": cfg.storage.qdrant.collection_name,
    }
