from __future__ import annotations

import os

from qdrant_client import QdrantClient

from backend.config_loader import OpenAgentSettings, QdrantConfig, load_config


def build_qdrant_client(q: QdrantConfig | None = None, *, settings: OpenAgentSettings | None = None) -> QdrantClient:
    """Construct ``QdrantClient`` from config (connection mode: location > path > url)."""
    qc = q if q is not None else (settings or load_config()).storage.qdrant
    api_key = os.environ.get(qc.api_key_env) if qc.api_key_env else None
    if qc.location:
        return QdrantClient(location=qc.location, api_key=api_key)
    if qc.path:
        return QdrantClient(path=qc.path, api_key=api_key)
    return QdrantClient(url=qc.url or "http://127.0.0.1:6333", api_key=api_key)
