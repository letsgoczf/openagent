from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from backend.config_loader import OpenAgentSettings, load_config
from backend.models.tokenizer import TokenizerService
from backend.rag.budget import RetrievalBudget
from backend.rag.citation import Citation, build_citations
from backend.rag.dense_recall import dense_recall
from backend.rag.evidence_builder import EvidenceEntry, build_evidence_entries
from backend.rag.keyword_recall import keyword_recall
from backend.rag.merge import merge_and_dedup
from backend.rag.reranker import rerank
from backend.storage.qdrant_store import QdrantStore
from backend.storage.sqlite_store import SQLiteStore


@dataclass
class RetrievalResult:
    """对齐 README_DESIGN：evidence + citations + retrieval_state；可选 candidate_debug。"""

    evidence_entries: list[EvidenceEntry]
    citations: list[Citation]
    retrieval_state: dict[str, Any]
    candidate_debug: dict[str, Any] | None = None


class RetrievalService:
    """
    在线 RAG 流水线：dense（Qdrant）→ keyword（FTS5）→ merge → rerank → EvidenceEntry → citations。

    设计依据：:file:`README_DESIGN.md`；混合加权与预算语义参考
    :file:`demo/04_rag_recipes.HybridRAG` / ``RAGSystem._retrieve`` 计时与可观测性。
    """

    def __init__(
        self,
        sqlite: SQLiteStore,
        qdrant: QdrantStore,
        tokenizer: TokenizerService,
        settings: OpenAgentSettings | None = None,
    ) -> None:
        self._sqlite = sqlite
        self._qdrant = qdrant
        self._tokenizer = tokenizer
        self._settings = settings or load_config()

    def retrieve(
        self,
        query: str,
        query_vector: list[float],
        *,
        version_scope: list[str] | None = None,
        budget: RetrievalBudget | None = None,
        top_k_dense: int | None = None,
        top_k_keyword: int | None = None,
        max_candidates: int | None = None,
        rerank_top_n: int | None = None,
        persist_evidence_cache: bool = True,
        candidate_debug: bool = False,
        allowed_collection_ids: list[str] | None = None,
    ) -> RetrievalResult:
        # P6: 受 RagRegistry 限制，拒绝访问未授权的 collection
        if allowed_collection_ids is not None:
            current_id = self._qdrant.collection_name
            if current_id not in allowed_collection_ids:
                return RetrievalResult(
                    evidence_entries=[],
                    citations=[],
                    retrieval_state={
                        "error": "collection_not_allowed",
                        "denied_id": current_id,
                        "allowed": allowed_collection_ids,
                    },
                )
        b = budget or RetrievalBudget.from_settings(self._settings)
        tk_d = top_k_dense if top_k_dense is not None else b.top_k_dense
        tk_k = top_k_keyword if top_k_keyword is not None else b.top_k_keyword
        max_c = max_candidates if max_candidates is not None else b.max_candidates
        r_top_n = rerank_top_n if rerank_top_n is not None else b.rerank_top_n
        w_d, w_k = b.w_dense, b.w_keyword

        allowed = self._settings.rag.allowed_origin_types
        origin_list = list(allowed) if allowed else None
        origin_frozen = frozenset(allowed) if allowed else None

        t0 = time.perf_counter()
        d_hits = dense_recall(
            self._qdrant,
            query_vector,
            top_k=tk_d,
            version_ids=version_scope,
        )
        t_dense = time.perf_counter()
        k_hits = keyword_recall(
            self._sqlite,
            query,
            top_k=tk_k,
            version_ids=version_scope,
            allowed_origin_types=origin_list,
        )
        t_kw = time.perf_counter()
        merged = merge_and_dedup(
            d_hits,
            k_hits,
            self._sqlite,
            max_candidates=max_c,
            w_dense=w_d,
            w_keyword=w_k,
            allowed_origin_types=origin_frozen,
        )
        t_merge = time.perf_counter()
        ranked = rerank(merged, top_n=r_top_n, settings=self._settings)
        t_rerank = time.perf_counter()

        max_tok = self._settings.evidence.max_evidence_entry_tokens
        entries = build_evidence_entries(
            ranked,
            self._sqlite,
            self._tokenizer,
            max_entry_tokens=max_tok,
            persist_cache=persist_evidence_cache,
        )
        cites = build_citations(entries, self._sqlite)
        t_end = time.perf_counter()

        rr = self._settings.rag.rerank
        state = {
            "dense_hits": len(d_hits),
            "keyword_hits": len(k_hits),
            "merged_candidates": len(merged),
            "reranked": len(ranked),
            "evidence_entries": len(entries),
            "citations": len(cites),
            "timings_ms": {
                "dense_recall": round((t_dense - t0) * 1000, 3),
                "keyword_recall": round((t_kw - t_dense) * 1000, 3),
                "merge": round((t_merge - t_kw) * 1000, 3),
                "rerank": round((t_rerank - t_merge) * 1000, 3),
                "evidence_and_citations": round((t_end - t_rerank) * 1000, 3),
                "retrieval_total": round((t_rerank - t0) * 1000, 3),
            },
            "rerank": {
                "strategy": rr.strategy,
                "model_id": rr.model_id,
            },
            "fusion": {
                "w_dense": w_d,
                "w_keyword": w_k,
            },
            "allowed_origin_types": origin_list,
            "rag_views": None,
        }

        debug: dict[str, Any] | None = None
        if candidate_debug:
            debug = {
                "dense_hits": d_hits,
                "keyword_hits": k_hits,
                "merged": [
                    {
                        "chunk_id": m.chunk_id,
                        "merged_score": m.merged_score,
                        "raw_dense": m.raw_dense,
                        "raw_keyword": m.raw_keyword,
                        "dense_norm": m.dense_norm,
                        "keyword_norm": m.keyword_norm,
                    }
                    for m in merged[: min(80, len(merged))]
                ],
            }

        return RetrievalResult(
            evidence_entries=entries,
            citations=cites,
            retrieval_state=state,
            candidate_debug=debug,
        )
