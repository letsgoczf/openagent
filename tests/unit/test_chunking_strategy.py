from __future__ import annotations

from backend.ingestion.chunking import chunk_text_by_tokens
from backend.models.tokenizer import TokenizerService


def test_chunking_respects_budget_and_overlap() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")
    # 构造多段文本
    text = "\n\n".join([("alpha " * 120).strip() for _ in range(6)])
    chunks = chunk_text_by_tokens(text, tok, max_chunk_tokens=200, overlap_tokens=20)
    assert len(chunks) >= 2
    for c in chunks:
        assert tok.count_tokens(c) <= 200

    # overlap：相邻 chunk 尾部与下一个开头应有一定重复（不要求严格相等，避免编码差异）
    t0 = tok.encode(chunks[0])
    t1 = tok.encode(chunks[1])
    assert len(set(t0[-20:]).intersection(set(t1[:40]))) >= 1


def test_chunking_keeps_markdown_headers_as_blocks() -> None:
    tok = TokenizerService(model_id="gpt-4o-mini")
    text = "# Title\n\npara one " + ("x " * 120) + "\n\n## Section\n\npara two " + ("y " * 120)
    chunks = chunk_text_by_tokens(text, tok, max_chunk_tokens=120, overlap_tokens=10)
    assert any("# Title" in c for c in chunks)
    assert any("## Section" in c for c in chunks)

