from __future__ import annotations

from types import SimpleNamespace

from backend.runners.composer import (
    body_references_evidence_index,
    maybe_format_citations_footer,
)


def test_body_references_requires_index_in_range() -> None:
    assert body_references_evidence_index("见 [1] 与 [3]。", 5) is True
    assert body_references_evidence_index("无编号", 3) is False
    assert body_references_evidence_index("超出 [99]", 5) is False


def test_maybe_footer_empty_when_no_bracket_ref() -> None:
    cites = [
        SimpleNamespace(
            chunk_id="a",
            version_id="v",
            location_summary="U1",
        )
    ]
    assert maybe_format_citations_footer(cites, "你好，不需要证据。") == ""


def test_maybe_footer_when_ref_present() -> None:
    cites = [
        SimpleNamespace(chunk_id="a", version_id="v", location_summary="U1"),
    ]
    out = maybe_format_citations_footer(cites, "依据 [1] 所述。")
    assert "Citations:" in out
    assert "chunk_id=a" in out
