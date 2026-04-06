from __future__ import annotations

from unittest.mock import MagicMock, patch

from backend.config_loader import (
    EmbeddingConfig,
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
from backend.kernel.budget import Budget
from backend.kernel.engine import KernelEngine
from backend.rag.citation import Citation
from backend.rag.evidence_builder import EvidenceEntry
from backend.rag.service import RetrievalResult


def _settings_simple(tmp_path) -> OpenAgentSettings:
    return OpenAgentSettings(
        models=ModelsConfig(
            generation=GenerationConfig(
                provider="ollama",
                model_id="tiny",
                base_url="http://127.0.0.1:11434",
            ),
            embedding=EmbeddingConfig(
                provider="ollama",
                model_id="nomic-embed-text",
                base_url="http://127.0.0.1:11434",
                vector_dimensions=4,
            ),
        ),
        storage=StorageConfig(
            sqlite_path=str(tmp_path / "engine.db"),
        ),
        tokenization=TokenizationConfig(provider="auto"),
        evidence=EvidenceConfig(max_evidence_entry_tokens=100),
        rag=RagConfig(
            recall=RagRecallConfig(
                top_k_dense=2,
                top_k_keyword=2,
                max_candidates=5,
                rerank_top_n=2,
            ),
            rerank=RagRerankConfig(strategy="merged_score"),
        ),
    )


@patch("backend.runners.chat_runner.embed_text", return_value=[1.0, 0.0, 0.0, 0.0])
@patch("backend.runners.chat_runner.build_qdrant_client")
@patch("backend.runners.chat_runner.create_llm_adapter")
@patch("backend.runners.chat_runner.RetrievalService")
def test_engine_trace_events_sequence(
    mock_rs_cls,
    mock_factory,
    mock_qclient,
    _mock_embed,
    tmp_path,
) -> None:
    mock_qclient.return_value = MagicMock()

    mock_factory.return_value = MagicMock()
    mock_factory.return_value.chat.return_value = "assistant reply"

    ent = EvidenceEntry(
        chunk_id="c1",
        version_id="v1",
        origin_type="text",
        location_summary="Page 1",
        evidence_snippet_text_v1="snip",
        evidence_entry_tokens_v1=1,
    )
    cite = Citation(
        chunk_id="c1",
        version_id="v1",
        source_span={"page_number": 1},
        location_summary="Page 1",
    )
    rr = RetrievalResult(
        evidence_entries=[ent],
        citations=[cite],
        retrieval_state={"dense_hits": 1},
        candidate_debug=None,
    )

    inst = MagicMock()
    inst.retrieve.return_value = rr
    mock_rs_cls.return_value = inst

    settings = _settings_simple(tmp_path)
    eng = KernelEngine(settings=settings)
    out = eng.run_chat("hello world", budget=Budget(max_llm_calls=3))

    assert "assistant reply" in out.answer
    assert "c1" in out.answer

    import sqlite3

    store_path = tmp_path / "engine.db"
    conn = sqlite3.connect(str(store_path))
    rows = conn.execute(
        "SELECT event_type FROM trace_event ORDER BY sequence_num"
    ).fetchall()
    types = [r[0] for r in rows]
    assert "run_started" in types
    assert "mode_selected" in types
    assert "retrieval_update" in types
    assert "evidence_update" in types
    assert "completed" in types
    conn.close()
