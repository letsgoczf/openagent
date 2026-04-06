"""与 ``backend/rag/demo/04_rag_recipes.py`` 中 RAG 配方对齐的辅助函数（教材用途 + 权重换算）。"""


def hybrid_weights_from_demo_keyword_weight(keyword_weight: float) -> tuple[float, float]:
    """
    ``HybridRAG`` 使用 ``keyword_weight`` 与 ``embedding_weight = 1 - keyword_weight``。
    OpenAgent 使用 ``w_keyword`` / ``w_dense``，与之逐项对应。
    """
    kw = max(0.0, min(1.0, float(keyword_weight)))
    return 1.0 - kw, kw
