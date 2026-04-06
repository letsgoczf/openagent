from __future__ import annotations

from typing import Any

from backend.storage.qdrant_store import QdrantStore


def dense_recall(
    store: QdrantStore,
    query_vector: list[float],
    *,
    top_k: int,
    version_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Qdrant dense top-k; optional ``version_ids`` scope (OR)."""
    hits = store.search(
        query_vector,
        limit=top_k,
        version_ids=version_ids,
    )
    return [
        {
            "chunk_id": h["chunk_id"],
            "version_id": h.get("version_id"),
            "dense_score": h.get("score"),
            "payload_meta": h.get("payload_meta") or {},
        }
        for h in hits
        if h.get("chunk_id")
    ]
