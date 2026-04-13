from __future__ import annotations

import tempfile
from pathlib import Path

from qdrant_client import QdrantClient

from backend.config_loader import load_config
from backend.kernel.budget import Budget
from backend.memory.fragment_extract import extract_fragments_from_turn
from backend.memory.reconstruct import (
    persist_turn_fragments,
    retrieve_reconstructed_fragment_context,
)
from backend.models.tokenizer import TokenizerService
from backend.runners.composer import build_messages
from backend.storage.qdrant_store import QdrantStore
from backend.storage.sqlite_store import SQLiteStore


def test_extract_fragments_from_turn_splits_paragraphs() -> None:
    fr = extract_fragments_from_turn(
        "What is the capital?",
        "Paris is the capital.\n\nLondon is another city with history.",
        max_frags=5,
        max_chars=200,
    )
    assert any("capital" in x.lower() for x in fr)
    assert len(fr) >= 2


def test_build_messages_includes_reconstructed_block() -> None:
    msgs = build_messages(
        constitution="C",
        query="Q",
        evidence_block="(none)",
        reconstructed_memory="• remembered fact",
    )
    assert "Retrieved memory fragments" in msgs[0]["content"]
    assert "remembered fact" in msgs[0]["content"]


def test_persist_and_retrieve_fragments_roundtrip(monkeypatch) -> None:
    settings0 = load_config()
    dim = int(settings0.models.embedding.vector_dimensions or 768)
    monkeypatch.setattr(
        "backend.memory.reconstruct.embed_text",
        lambda text, settings=None, **kw: [0.15] * dim,
    )

    settings = load_config()
    mem = settings.memory.model_copy(
        update={
            "fragments_extract_max": 4,
            "fragment_top_k": 4,
            "fragment_max_chars": 300,
            "fragment_context_max_tokens": 500,
        }
    )
    settings = settings.model_copy(update={"memory": mem})

    client = QdrantClient(location=":memory:")
    mem_q = QdrantStore("test_mem_frag", dim, client=client)

    tok = TokenizerService(model_id="gpt-4o-mini")
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "m.db"
        store = SQLiteStore(db)
        sid = "s_frag"
        persist_turn_fragments(
            store,
            mem_q,
            settings,
            sid,
            "run_x",
            "User asks about alpha",
            "Alpha is a concept. Beta follows alpha in order.",
            None,
            budget=Budget(max_llm_calls=4),
            llm=None,
        )
        ctx = retrieve_reconstructed_fragment_context(
            store, mem_q, settings, sid, "tell me about alpha", tok
        )
        assert "alpha" in ctx.lower()
        store.close()
