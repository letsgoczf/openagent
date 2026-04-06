from __future__ import annotations

import math
import uuid

from backend.config_loader import (
    EvidenceConfig,
    GenerationConfig,
    ModelsConfig,
    OpenAgentSettings,
    RagConfig,
    RagRecallConfig,
    RagRerankConfig,
    StorageConfig,
    TokenizationConfig,
)
from backend.rag.budget import RetrievalBudget
from backend.rag.recipes_bridge import hybrid_weights_from_demo_keyword_weight
from backend.models.tokenizer import TokenizerService
from backend.rag.citation import build_citations, citation_chunk_ids_subset
from backend.rag.evidence_builder import truncate_to_token_budget
from backend.rag.merge import merge_and_dedup
from backend.rag.service import RetrievalService
from backend.storage.qdrant_store import QdrantStore
from backend.storage.sqlite_store import SQLiteStore


def _settings() -> OpenAgentSettings:
    return OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="llama3.2",
                base_url="http://127.0.0.1:11434",
            ),
        ),
        storage=StorageConfig(),
        tokenization=TokenizationConfig(provider="auto"),
        evidence=EvidenceConfig(max_evidence_entry_tokens=80),
        rag=RagConfig(
            recall=RagRecallConfig(
                top_k_dense=5,
                top_k_keyword=5,
                max_candidates=20,
                rerank_top_n=5,
                w_dense=0.7,
                w_keyword=0.3,
            ),
            rerank=RagRerankConfig(strategy="merged_score"),
        ),
    )


def test_merge_dedup_single_chunk() -> None:
    store = SQLiteStore(":memory:")
    doc_id, ver_id = str(uuid.uuid4()), str(uuid.uuid4())
    cid = str(uuid.uuid4())
    store.insert_document(doc_id, "/x", "x.pdf", "pdf")
    store.insert_document_version(ver_id, doc_id, "h", "ev1", "tok", "ready")
    store.insert_chunk(cid, ver_id, "text", 0, "hello", {"page_number": 1}, page_number=1)

    dense = [{"chunk_id": cid, "version_id": ver_id, "dense_score": 0.9}] * 3
    kw = [{"chunk_id": cid, "score": -1.0}, {"chunk_id": cid, "score": -2.0}]
    merged = merge_and_dedup(dense, kw, store, max_candidates=50)
    assert len(merged) == 1
    assert merged[0].chunk_id == cid


def test_merge_stable_order() -> None:
    store = SQLiteStore(":memory:")
    doc_id, ver_id = str(uuid.uuid4()), str(uuid.uuid4())
    store.insert_document(doc_id, "/x", "x.pdf", "pdf")
    store.insert_document_version(ver_id, doc_id, "h", "ev1", "tok", "ready")
    ids = []
    for i in range(3):
        cid = str(uuid.uuid4())
        ids.append(cid)
        store.insert_chunk(
            cid, ver_id, "text", i, f"chunk {i} zuniq{i}", {"page_number": i}, page_number=i
        )
    dense = [{"chunk_id": ids[2], "dense_score": 0.5}, {"chunk_id": ids[1], "dense_score": 0.5}]
    kw: list[dict] = []
    m1 = merge_and_dedup(dense, kw, store)
    m2 = merge_and_dedup(dense, kw, store)
    assert [x.chunk_id for x in m1] == [x.chunk_id for x in m2]


def test_evidence_token_cache_persisted(tmp_path) -> None:
    db = tmp_path / "e.db"
    store = SQLiteStore(db)
    doc_id, ver_id = str(uuid.uuid4()), str(uuid.uuid4())
    cid = str(uuid.uuid4())
    store.insert_document(doc_id, "/x", "x.pdf", "pdf")
    store.insert_document_version(ver_id, doc_id, "h", "ev1", "tok", "ready")
    long_text = "word " * 200
    store.insert_chunk(cid, ver_id, "text", 0, long_text, {"page_number": 1}, page_number=1)

    qd = QdrantStore("rag_t", vector_size=4, location=":memory:")
    qd.ensure_collection()
    tok = TokenizerService(model_id="gpt-4")

    svc = RetrievalService(store, qd, tok, settings=_settings())
    vec = [1.0, 0.0, 0.0, 0.0]
    qd.upsert_embedding(
        vec,
        chunk_id=cid,
        version_id=ver_id,
        origin_type="text",
        unit_type="pdf_page",
        unit_number=1,
    )

    r1 = svc.retrieve(
        "word",
        vec,
        version_scope=[ver_id],
        top_k_dense=5,
        top_k_keyword=5,
        rerank_top_n=5,
        persist_evidence_cache=True,
    )
    assert r1.evidence_entries
    row = store.get_chunk_by_id(cid)
    assert row is not None
    assert row.get("evidence_snippet_text_v1") is not None
    assert row.get("evidence_entry_tokens_v1") is not None
    first_snip = row["evidence_snippet_text_v1"]
    first_tok = row["evidence_entry_tokens_v1"]

    r2 = svc.retrieve(
        "word",
        vec,
        version_scope=[ver_id],
        top_k_dense=5,
        top_k_keyword=5,
        rerank_top_n=5,
        persist_evidence_cache=True,
    )
    row2 = store.get_chunk_by_id(cid)
    assert row2["evidence_snippet_text_v1"] == first_snip
    assert row2["evidence_entry_tokens_v1"] == first_tok

    store.close()
    qd.close()


def test_citations_have_source_span() -> None:
    store = SQLiteStore(":memory:")
    doc_id, ver_id = str(uuid.uuid4()), str(uuid.uuid4())
    cid = str(uuid.uuid4())
    store.insert_document(doc_id, "/x", "x.pdf", "pdf")
    store.insert_document_version(ver_id, doc_id, "h", "ev1", "tok", "ready")
    span = {"page_number": 3, "para": 2}
    store.insert_chunk(
        cid,
        ver_id,
        "text",
        0,
        "body",
        span,
        page_number=3,
        evidence_snippet_text_v1="body",
        evidence_entry_tokens_v1=1,
    )

    from backend.rag.evidence_builder import EvidenceEntry

    entries = [
        EvidenceEntry(
            chunk_id=cid,
            version_id=ver_id,
            origin_type="text",
            location_summary="Page 3",
            evidence_snippet_text_v1="body",
            evidence_entry_tokens_v1=1,
        )
    ]
    cites = build_citations(entries, store)
    assert len(cites) == 1
    assert cites[0].source_span.get("page_number") == 3
    assert cites[0].chunk_id == cid
    assert citation_chunk_ids_subset({cid}, [c.chunk_id for c in cites])


def test_hybrid_weights_match_demo_recipe() -> None:
    wd, wk = hybrid_weights_from_demo_keyword_weight(0.3)
    assert abs(wd - 0.7) < 1e-9 and abs(wk - 0.3) < 1e-9
    b = RetrievalBudget.from_settings(_settings())
    assert math.isclose(b.w_dense + b.w_keyword, 1.0)


def test_retrieval_candidate_debug_flag(tmp_path) -> None:
    db = tmp_path / "d.db"
    store = SQLiteStore(db)
    doc_id, ver_id = str(uuid.uuid4()), str(uuid.uuid4())
    cid = str(uuid.uuid4())
    store.insert_document(doc_id, "/x", "x.pdf", "pdf")
    store.insert_document_version(ver_id, doc_id, "h", "ev1", "tok", "ready")
    store.insert_chunk(cid, ver_id, "text", 0, "alpha beta", {"page_number": 1}, page_number=1)
    qd = QdrantStore("c", vector_size=4, location=":memory:")
    qd.ensure_collection()
    vec = [1.0, 0.0, 0.0, 0.0]
    qd.upsert_embedding(
        vec,
        chunk_id=cid,
        version_id=ver_id,
        origin_type="text",
        unit_type="pdf_page",
        unit_number=1,
    )
    svc = RetrievalService(store, qd, TokenizerService(model_id="gpt-4"), settings=_settings())
    r = svc.retrieve("alpha", vec, version_scope=[ver_id], candidate_debug=True)
    assert r.candidate_debug is not None
    assert any(h.get("chunk_id") == cid for h in r.candidate_debug["dense_hits"])
    store.close()
    qd.close()


def test_truncate_respects_budget() -> None:
    tok = TokenizerService(encoding_name="cl100k_base")
    t = "hello " * 100
    out = truncate_to_token_budget(t, tok, max_tokens=5)
    assert tok.count_tokens(out) <= 5
    assert len(out) < len(t)
