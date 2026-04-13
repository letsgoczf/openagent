from __future__ import annotations

import uuid

from backend.config_loader import OpenAgentSettings
from backend.kernel.budget import Budget
from backend.kernel.trace import TraceWriter
from backend.memory.fragment_extract import extract_fragments_from_turn
from backend.memory.fragment_llm import (
    extract_fragments_via_llm,
    reconstruct_context_via_llm,
)
from backend.memory.session_store import trim_summary_to_budget
from backend.models.base import LLMAdapter
from backend.models.embeddings import embed_text
from backend.models.tokenizer import TokenizerService
from backend.storage.qdrant_store import QdrantStore
from backend.storage.sqlite_store import SQLiteStore


def embedding_vector_size(settings: OpenAgentSettings) -> int:
    d = settings.models.embedding.vector_dimensions
    if d is not None:
        return int(d)
    return len(embed_text("ping", settings=settings))


def _assemble_template_fragment_blob(
    store: SQLiteStore,
    mem_qdrant: QdrantStore,
    settings: OpenAgentSettings,
    session_id: str,
    query: str,
    cfg,
) -> tuple[str, list[str]]:
    """向量检索 + 模板拼接；返回 (blob, fragment_ids_used)。"""
    try:
        qvec = embed_text(query, settings=settings)
    except Exception:  # noqa: BLE001
        return "", []
    if not qvec:
        return "", []

    try:
        hits = mem_qdrant.search_memory_fragments(
            qvec, session_id=session_id, limit=cfg.fragment_top_k
        )
    except Exception:  # noqa: BLE001
        return "", []

    lines: list[str] = []
    ids: list[str] = []
    seen: set[str] = set()
    for h in hits:
        fid = h.get("fragment_id")
        if not fid:
            continue
        fs = str(fid)
        if fs in seen:
            continue
        seen.add(fs)
        row = store.get_memory_fragment(fs)
        if not row:
            continue
        t = str(row["text"]).strip().replace("\n", " ")
        if len(t) > cfg.fragment_max_chars:
            t = t[: cfg.fragment_max_chars] + "…"
        lines.append(f"• {t}")
        ids.append(fs)

    return "\n".join(lines), ids


def retrieve_reconstructed_fragment_context(
    store: SQLiteStore,
    mem_qdrant: QdrantStore,
    settings: OpenAgentSettings,
    session_id: str,
    query: str,
    tokenizer: TokenizerService,
    *,
    budget: Budget | None = None,
    llm: LLMAdapter | None = None,
    trace: TraceWriter | None = None,
) -> str:
    """按 query 稠密检索同 session 片段；可选 LLM 重构，否则模板组装。"""
    cfg = settings.memory
    if not cfg.enabled or not cfg.fragments_enabled or cfg.fragment_top_k <= 0:
        return ""

    template_blob, _ids = _assemble_template_fragment_blob(
        store, mem_qdrant, settings, session_id, query, cfg
    )
    if not template_blob.strip():
        return ""

    if (
        cfg.reconstruct_llm_enabled
        and llm is not None
        and budget is not None
    ):
        fused = reconstruct_context_via_llm(
            llm=llm,
            budget=budget,
            cfg=cfg,
            query=query,
            template_blob=template_blob,
            tokenizer=tokenizer,
            trace=trace,
        )
        if fused and fused.strip():
            return trim_summary_to_budget(
                fused.strip(), tokenizer, cfg.fragment_context_max_tokens
            )

    return trim_summary_to_budget(
        template_blob, tokenizer, cfg.fragment_context_max_tokens
    )


def persist_turn_fragments(
    store: SQLiteStore,
    mem_qdrant: QdrantStore,
    settings: OpenAgentSettings,
    session_id: str,
    run_id: str,
    user_text: str,
    assistant_text: str,
    trace: TraceWriter | None,
    *,
    budget: Budget | None = None,
    llm: LLMAdapter | None = None,
) -> None:
    cfg = settings.memory
    if not cfg.enabled or not cfg.fragments_enabled:
        return

    texts: list[str] = []
    if cfg.fragment_llm_extraction_enabled and llm is not None and budget is not None:
        texts = extract_fragments_via_llm(
            llm=llm,
            budget=budget,
            cfg=cfg,
            user_text=user_text,
            assistant_text=assistant_text,
            trace=trace,
        )

    if not texts:
        texts = extract_fragments_from_turn(
            user_text,
            assistant_text,
            max_frags=cfg.fragments_extract_max,
            max_chars=cfg.fragment_max_chars,
        )
        if trace and cfg.fragment_llm_extraction_enabled:
            trace.emit(
                "memory_fragment_extract_fallback",
                {"reason": "rules_after_llm_empty_or_disabled", "count": len(texts)},
            )

    if not texts:
        return

    n = 0
    for t in texts:
        raw = t.strip()
        if not raw:
            continue
        embed_src = raw[:2000]
        fid = str(uuid.uuid4())
        try:
            store.insert_memory_fragment(
                fid, session_id, run_id, "episodic", raw
            )
        except Exception:  # noqa: BLE001
            continue
        try:
            vec = embed_text(embed_src, settings=settings)
            if not vec:
                continue
            mem_qdrant.upsert_memory_fragment(
                vec, fragment_id=fid, session_id=session_id
            )
            n += 1
        except Exception:  # noqa: BLE001
            continue

    if trace is not None and n > 0:
        trace.emit("memory_fragments_write", {"count": n})
