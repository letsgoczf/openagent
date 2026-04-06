from __future__ import annotations

from dataclasses import dataclass

from backend.storage.sqlite_store import SQLiteStore


@dataclass
class MergedCandidate:
    chunk_id: str
    version_id: str
    merged_score: float
    dense_norm: float | None
    keyword_norm: float | None
    raw_dense: float | None
    raw_keyword: float | None


def _dedup_dense_best(hits: list[dict]) -> dict[str, float]:
    """Keep max cosine per chunk_id (higher is better)."""
    best: dict[str, float] = {}
    for h in hits:
        cid = h["chunk_id"]
        if h.get("dense_score") is None:
            continue
        s = float(h["dense_score"])
        best[cid] = max(best.get(cid, float("-inf")), s)
    return {k: v for k, v in best.items() if v > float("-inf")}


def _dedup_keyword_best(hits: list[dict]) -> dict[str, float]:
    """Keep min bm25 per chunk_id (lower is better)."""
    best: dict[str, float] = {}
    for h in hits:
        cid = h["chunk_id"]
        s = float(h["score"])
        if cid not in best:
            best[cid] = s
        else:
            best[cid] = min(best[cid], s)
    return best


def _norm_by_chunk(
    score_by_chunk: dict[str, float],
    *,
    higher_is_better: bool,
) -> dict[str, float]:
    """Min-max to [0, 1] per chunk keys; higher value = better match."""
    if not score_by_chunk:
        return {}
    vals = list(score_by_chunk.values())
    lo, hi = min(vals), max(vals)
    out: dict[str, float] = {}
    if hi <= lo:
        for k in score_by_chunk:
            out[k] = 1.0
        return out
    for k, v in score_by_chunk.items():
        if higher_is_better:
            out[k] = (v - lo) / (hi - lo)
        else:
            out[k] = (hi - v) / (hi - lo)
    return out


def merge_and_dedup(
    dense_hits: list[dict],
    keyword_hits: list[dict],
    sqlite: SQLiteStore,
    *,
    max_candidates: int = 120,
    w_dense: float = 0.5,
    w_keyword: float = 0.5,
    allowed_origin_types: frozenset[str] | None = None,
) -> list[MergedCandidate]:
    """chunk_id 去重；dense / keyword 各自 min-max 归一后加权合成 merged_score（可选来源过滤）。"""
    dense_map = _dedup_dense_best(dense_hits)
    kw_map = _dedup_keyword_best(keyword_hits)

    dense_norm = _norm_by_chunk(dense_map, higher_is_better=True)
    kw_norm = _norm_by_chunk(kw_map, higher_is_better=False)

    chunk_ids = set(dense_map) | set(kw_map)
    if not chunk_ids:
        return []

    rows = sqlite.get_chunks_by_ids(list(chunk_ids))

    candidates: list[MergedCandidate] = []
    for cid in sorted(chunk_ids):
        row = rows.get(cid)
        if row is None:
            continue
        if allowed_origin_types and row.get("origin_type") not in allowed_origin_types:
            continue
        vid = row["version_id"]
        rd = dense_map.get(cid)
        rk = kw_map.get(cid)
        dn = dense_norm.get(cid) if rd is not None else None
        kn = kw_norm.get(cid) if rk is not None else None
        if dn is not None and kn is not None:
            merged = w_dense * dn + w_keyword * kn
        elif dn is not None:
            merged = dn
        elif kn is not None:
            merged = kn
        else:
            merged = 0.0
        candidates.append(
            MergedCandidate(
                chunk_id=cid,
                version_id=vid,
                merged_score=merged,
                dense_norm=dn,
                keyword_norm=kn,
                raw_dense=rd,
                raw_keyword=rk,
            )
        )

    candidates.sort(key=lambda c: (-c.merged_score, c.chunk_id))
    return candidates[:max_candidates]
