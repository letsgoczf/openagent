from __future__ import annotations

from typing import Any

from backend.storage.sqlite_store import SQLiteStore


def sanitize_fts5_query(raw: str) -> str:
    """Minimal sanitization for FTS5 MATCH; avoids empty / broken phrases."""
    q = raw.replace('"', " ").replace("'", " ").strip()
    if not q:
        return '""'
    return q


def keyword_recall(
    store: SQLiteStore,
    query: str,
    *,
    top_k: int,
    version_ids: list[str] | None = None,
    allowed_origin_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """SQLite FTS5 top-k; bm25 score (lower is better)."""
    sq = sanitize_fts5_query(query)
    return store.query_fts5(
        sq,
        limit=top_k,
        version_ids=version_ids,
        origin_types=allowed_origin_types,
    )

