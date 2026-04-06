from __future__ import annotations

from backend.config_loader import OpenAgentSettings, load_config
from backend.rag.merge import MergedCandidate


def rerank(
    candidates: list[MergedCandidate],
    *,
    top_n: int,
    settings: OpenAgentSettings | None = None,
) -> list[MergedCandidate]:
    """
    MVP：``merged_score`` 排序；与 ``settings.rag.rerank.strategy`` 对齐，
    ``cross_encoder`` 预留（当前仍按 merged 排序，避免未实现时静默失败）。
    """
    cfg = settings or load_config()
    strategy = cfg.rag.rerank.strategy
    _ = strategy  # cross_encoder hook for later
    ordered = sorted(candidates, key=lambda c: (-c.merged_score, c.chunk_id))
    return ordered[:top_n]
