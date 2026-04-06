"""RAG: dense + keyword recall, merge, rerank, evidence, citations.

设计见 ``README_DESIGN.md``；混合检索与权重语义参考 ``demo/04_rag_recipes.py``（HybridRAG）。
"""

from backend.rag.budget import RetrievalBudget
from backend.rag.citation import Citation, build_citations, citation_chunk_ids_subset
from backend.rag.evidence_builder import EvidenceEntry, build_evidence_entries
from backend.rag.merge import MergedCandidate, merge_and_dedup
from backend.rag.recipes_bridge import hybrid_weights_from_demo_keyword_weight
from backend.rag.service import RetrievalResult, RetrievalService

__all__ = [
    "Citation",
    "EvidenceEntry",
    "MergedCandidate",
    "RetrievalBudget",
    "RetrievalResult",
    "RetrievalService",
    "build_citations",
    "build_evidence_entries",
    "citation_chunk_ids_subset",
    "hybrid_weights_from_demo_keyword_weight",
    "merge_and_dedup",
]
