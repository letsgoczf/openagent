from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from backend.models.tokenizer import TokenizerService
from backend.rag.merge import MergedCandidate
from backend.storage.sqlite_store import SQLiteStore


class EvidenceEntry(BaseModel):
    chunk_id: str
    version_id: str
    origin_type: Literal["text", "table", "ocr"]
    location_summary: str
    evidence_snippet_text_v1: str
    evidence_entry_tokens_v1: int
    dense_score: float | None = None
    keyword_score: float | None = None
    rerank_score: float | None = None


def build_location_summary(row: dict[str, Any]) -> str:
    """Human-readable location for citations (v1)."""
    page = row.get("page_number")
    slide = row.get("slide_number")
    tbl = row.get("table_id")
    if slide is not None:
        base = f"Slide {slide}"
    elif page is not None:
        base = f"Page {page}"
    else:
        # 非 PDF / 非 PPTX：回退到 source_span 中的 unit_index
        span = row.get("source_span") or {}
        unit = span.get("unit_index")
        if isinstance(unit, int):
            base = f"Unit {unit}"
        else:
            base = "Unknown location"
    if tbl:
        base += f", Table {tbl}"
    return base


def truncate_to_token_budget(text: str, tokenizer: TokenizerService, max_tokens: int) -> str:
    if max_tokens <= 0 or not text:
        return ""
    if tokenizer.count_tokens(text) <= max_tokens:
        return text
    lo, hi = 0, len(text)
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        snippet = text[:mid]
        n = tokenizer.count_tokens(snippet)
        if n <= max_tokens:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return text[:best]


def build_evidence_entries(  # noqa: PLR0913
    ranked: list[MergedCandidate],
    sqlite: SQLiteStore,
    tokenizer: TokenizerService,
    *,
    max_entry_tokens: int,
    persist_cache: bool = True,
) -> list[EvidenceEntry]:
    """Assemble EvidenceEntry v1; refresh snippet + token cache when missing or empty."""
    rows = sqlite.get_chunks_by_ids([c.chunk_id for c in ranked])
    entries: list[EvidenceEntry] = []

    for cand in ranked:
        row = rows.get(cand.chunk_id)
        if row is None:
            continue
        origin = row["origin_type"]
        if origin not in ("text", "table", "ocr"):
            origin = "text"

        cached_snip = row.get("evidence_snippet_text_v1")
        cached_tok = row.get("evidence_entry_tokens_v1")
        full_text = row["chunk_text"] or ""

        if cached_snip and cached_tok is not None:
            snippet = cached_snip
            ntok = int(cached_tok)
        else:
            snippet = truncate_to_token_budget(full_text, tokenizer, max_entry_tokens)
            ntok = tokenizer.count_tokens(snippet)
            if persist_cache:
                sqlite.update_chunk_evidence_cache(
                    cand.chunk_id,
                    evidence_entry_tokens_v1=ntok,
                    evidence_snippet_text_v1=snippet,
                )

        loc = build_location_summary(row)
        entries.append(
            EvidenceEntry(
                chunk_id=cand.chunk_id,
                version_id=cand.version_id,
                origin_type=origin,  # type: ignore[arg-type]
                location_summary=loc,
                evidence_snippet_text_v1=snippet,
                evidence_entry_tokens_v1=ntok,
                dense_score=cand.raw_dense,
                keyword_score=cand.raw_keyword,
                rerank_score=cand.merged_score,
            )
        )

    return entries
