from __future__ import annotations

from backend.models.tokenizer import TokenizerService
from backend.runners.composer import trim_evidence_entries_to_budget
from backend.rag.evidence_builder import EvidenceEntry


def test_trim_evidence_entries_to_budget_keeps_some() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")  # 若未知会回退 cl100k_base
    entries = [
        EvidenceEntry(
            chunk_id="c1",
            version_id="v",
            origin_type="text",
            location_summary="Unit 1",
            evidence_snippet_text_v1="hello " * 400,
            evidence_entry_tokens_v1=tok.count_tokens("hello " * 400),
        ),
        EvidenceEntry(
            chunk_id="c2",
            version_id="v",
            origin_type="text",
            location_summary="Unit 2",
            evidence_snippet_text_v1="world " * 400,
            evidence_entry_tokens_v1=tok.count_tokens("world " * 400),
        ),
    ]

    trimmed = trim_evidence_entries_to_budget(entries, tok, max_assembled_tokens=200)
    assert len(trimmed) >= 1
    assert trimmed[0].chunk_id == "c1"


def test_trim_evidence_entries_to_budget_limits_count() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")
    entries = []
    for i in range(10):
        txt = "abc " * 80
        entries.append(
            EvidenceEntry(
                chunk_id=f"c{i}",
                version_id="v",
                origin_type="text",
                location_summary=f"Unit {i}",
                evidence_snippet_text_v1=txt,
                evidence_entry_tokens_v1=tok.count_tokens(txt),
            )
        )
    trimmed = trim_evidence_entries_to_budget(entries, tok, max_assembled_tokens=400)
    assert 1 <= len(trimmed) < len(entries)

