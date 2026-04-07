from __future__ import annotations

import re

from backend.models.tokenizer import TokenizerService


_WS_RE = re.compile(r"[ \t]+")


def _normalize_text(text: str) -> str:
    # 保留换行结构，但去掉行尾多余空白，避免 token 浪费
    lines = [(_WS_RE.sub(" ", ln)).rstrip() for ln in (text or "").splitlines()]
    return "\n".join(lines).strip()


def _split_markdownish_blocks(text: str) -> list[str]:
    """
    结构优先分块：
    - 先按空行把段落切开
    - 保留 Markdown 标题行与其后内容的天然边界（标题自身作为块）
    """
    t = _normalize_text(text)
    if not t:
        return []

    blocks: list[str] = []
    cur: list[str] = []
    for raw_line in t.splitlines():
        line = raw_line.rstrip()
        if not line:
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
            continue
        # Markdown 标题：独立成块，尽量不与前段拼接
        if line.startswith("#"):
            if cur:
                blocks.append("\n".join(cur).strip())
                cur = []
            blocks.append(line.strip())
            continue
        cur.append(line)
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


def _ensure_token_budget(
    block: str,
    tokenizer: TokenizerService,
    *,
    max_tokens: int,
) -> list[str]:
    """
    如果单个 block 本身就超过 max_tokens，则按 token 硬切为若干段。
    这是最后兜底，保证不会把超长块直接送去 embedding。
    """
    if max_tokens <= 0:
        return []
    tok = tokenizer.encode(block)
    if len(tok) <= max_tokens:
        return [block]
    out: list[str] = []
    for i in range(0, len(tok), max_tokens):
        piece = tokenizer.decode(tok[i : i + max_tokens]).strip()
        if piece:
            out.append(piece)
    return out


def chunk_text_by_tokens(
    text: str,
    tokenizer: TokenizerService,
    *,
    max_chunk_tokens: int = 800,
    overlap_tokens: int = 80,
) -> list[str]:
    """
    依据 RAG chunking 原则：
    - **Budget**：每块不超过 max_chunk_tokens
    - **Recall 友好**：优先在段落/标题边界切分
    - **连续性**：相邻块按 overlap_tokens 叠加，提升跨块检索命中
    """
    if max_chunk_tokens <= 0:
        return []
    if overlap_tokens < 0:
        overlap_tokens = 0
    if overlap_tokens >= max_chunk_tokens:
        overlap_tokens = max(0, max_chunk_tokens // 5)

    blocks0 = _split_markdownish_blocks(text)
    if not blocks0:
        return []

    # 先把过大的 block 兜底切开，再做“段落拼装成 chunk”
    blocks: list[str] = []
    for b in blocks0:
        blocks.extend(_ensure_token_budget(b, tokenizer, max_tokens=max_chunk_tokens))

    chunks: list[str] = []
    cur_tokens: list[int] = []
    cur_texts: list[str] = []

    def flush() -> None:
        nonlocal cur_tokens, cur_texts
        if cur_texts:
            s = "\n\n".join(cur_texts).strip()
            if s:
                chunks.append(s)
        if overlap_tokens > 0 and cur_tokens:
            ov = cur_tokens[-overlap_tokens:]
            # overlap 作为下一块的起始 token（用 decode 还原）
            cur_tokens = list(ov)
            ov_text = tokenizer.decode(cur_tokens).strip()
            cur_texts = [ov_text] if ov_text else []
        else:
            cur_tokens = []
            cur_texts = []

    for b in blocks:
        btok = tokenizer.encode(b)
        if not btok:
            continue
        # 如果当前块为空，直接起
        if not cur_tokens:
            cur_tokens = list(btok)
            cur_texts = [b]
            continue

        # 尝试把 b 拼到当前 chunk（用 token 精确预算）
        sep_tokens = tokenizer.encode("\n\n")
        merged_len = len(cur_tokens) + len(sep_tokens) + len(btok)
        if merged_len <= max_chunk_tokens:
            cur_tokens.extend(sep_tokens)
            cur_tokens.extend(btok)
            cur_texts.append(b)
            continue

        # 否则先 flush 当前，再开始新块
        flush()
        cur_tokens = list(btok)
        cur_texts = [b]

    flush()
    return chunks

