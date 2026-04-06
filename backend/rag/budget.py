from __future__ import annotations

from dataclasses import dataclass

from backend.config_loader import OpenAgentSettings


@dataclass
class RetrievalBudget:
    """
    在线检索预算（README_DESIGN §2：候选规模 / 证据条数），可由配置或调用方覆盖。
    权重字段与 ``demo/04_rag_recipes.HybridRAG`` 的语义/关键词双通道融合一致。
    """

    top_k_dense: int
    top_k_keyword: int
    max_candidates: int
    rerank_top_n: int
    w_dense: float
    w_keyword: float

    @classmethod
    def from_settings(cls, settings: OpenAgentSettings) -> RetrievalBudget:
        r = settings.rag.recall
        return cls(
            top_k_dense=r.top_k_dense,
            top_k_keyword=r.top_k_keyword,
            max_candidates=r.max_candidates,
            rerank_top_n=r.rerank_top_n,
            w_dense=r.w_dense,
            w_keyword=r.w_keyword,
        )
