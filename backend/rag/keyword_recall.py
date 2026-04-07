from __future__ import annotations

import re
from typing import Any

from backend.storage.sqlite_store import SQLiteStore


def sanitize_fts5_query(raw: str) -> str:
    """
    将自然语言查询转为 FTS5 安全词串，避免 `-` / 布尔运算符等触发语法错误。
    返回形式为 `token1 token2 ...`（AND 语义）。
    """
    q = (raw or "").strip().lower()
    if not q:
        return '""'
    # 去掉会影响 MATCH 语法的符号；保留中英文数字与空白
    q = re.sub(r'["\'`]', " ", q)
    q = re.sub(r"[\-\:\(\)\{\}\[\]\+\*\^\~\!\?\\\/\|<>=&,;]", " ", q)
    # 布尔关键字当作噪声词移除
    q = re.sub(r"\b(and|or|not|near)\b", " ", q, flags=re.IGNORECASE)
    toks = [t for t in re.split(r"\s+", q) if t]
    if not toks:
        return '""'
    # 限制关键词数量，避免超长 MATCH
    return " ".join(toks[:24])


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
    try:
        return store.query_fts5(
            sq,
            limit=top_k,
            version_ids=version_ids,
            origin_types=allowed_origin_types,
        )
    except Exception:  # noqa: BLE001
        # 降级：keyword 通道失败时不阻断整条 RAG 链路
        return []

