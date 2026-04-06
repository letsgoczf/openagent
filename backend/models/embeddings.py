from __future__ import annotations

import os

from openai import OpenAI
import ollama

from backend.config_loader import EmbeddingConfig, OpenAgentSettings, load_config
from backend.models.ollama_client_util import ollama_httpx_kwargs


def embed_text(
    text: str,
    *,
    settings: OpenAgentSettings | None = None,
    embedding: EmbeddingConfig | None = None,
) -> list[float]:
    """根据配置生成查询向量（dense recall 用）。"""
    cfg = embedding or (settings or load_config()).models.embedding
    if cfg.provider == "openai":
        key = os.environ.get(cfg.api_key_env or "OPENAI_API_KEY", "")
        client = OpenAI(api_key=key or None, base_url=cfg.base_url)
        r = client.embeddings.create(model=cfg.model_id, input=text)
        return list(r.data[0].embedding)
    if cfg.provider == "ollama":
        host = cfg.base_url or "http://127.0.0.1:11434"
        client = ollama.Client(host=host, **ollama_httpx_kwargs(host))
        r = client.embed(model=cfg.model_id, input=text)
        return list(r.embeddings[0])
    if cfg.provider == "vllm":
        if not cfg.base_url:
            msg = "vLLM embedding requires models.embedding.base_url"
            raise ValueError(msg)
        key = None
        if cfg.api_key_env:
            key = os.environ.get(cfg.api_key_env) or None
        client = OpenAI(
            api_key=key or "EMPTY",
            base_url=(cfg.base_url or "").rstrip("/"),
        )
        r = client.embeddings.create(model=cfg.model_id, input=text)
        return list(r.data[0].embedding)
    raise ValueError(f"Unknown embedding provider: {cfg.provider}")
