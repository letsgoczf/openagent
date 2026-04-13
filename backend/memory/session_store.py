from __future__ import annotations

from backend.config_loader import MemoryConfig
from backend.models.tokenizer import TokenizerService
from backend.storage.sqlite_store import SQLiteStore


def trim_summary_to_budget(
    text: str,
    tokenizer: TokenizerService,
    max_tokens: int,
) -> str:
    if max_tokens <= 0 or not text.strip():
        return ""
    t = text.strip()
    if tokenizer.count_tokens(t) <= max_tokens:
        return t
    lo, hi = 0, len(t)
    best = ""
    while lo <= hi:
        mid = (lo + hi) // 2
        chunk = t[:mid].rstrip()
        if not chunk:
            break
        if tokenizer.count_tokens(chunk) <= max_tokens:
            best = chunk
            lo = mid + 1
        else:
            hi = mid - 1
    return best or t[:200]


def trim_history_messages_to_budget(
    messages: list[dict[str, str]],
    tokenizer: TokenizerService,
    max_tokens: int,
) -> list[dict[str, str]]:
    """从最新一条向前累加，保留能放进预算内的最早起始切片（顺序不变）。"""
    if max_tokens <= 0 or not messages:
        return []
    total = 0
    start = len(messages)
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        content = m.get("content") or ""
        n = tokenizer.count_tokens(content)
        if total + n > max_tokens:
            break
        total += n
        start = i
    return messages[start:]


def fetch_history_messages(
    store: SQLiteStore,
    cfg: MemoryConfig,
    session_id: str,
    tokenizer: TokenizerService,
) -> tuple[list[dict[str, str]], str | None]:
    """
    返回 (verbatim 历史消息, 滚动摘要文本)。
    Phase B：开启 consolidation 时用 ``covers_until_id`` + 摘要表；否则同 Phase A。
    """
    if not cfg.enabled or cfg.session_max_turns <= 0:
        return [], None

    rolling_summary: str | None = None
    covers_until_id = 0

    if cfg.consolidation_enabled:
        row = store.get_chat_session_summary(session_id)
        if row:
            covers_until_id = int(row["covers_until_id"])
            st = (row["summary_text"] or "").strip()
            if st:
                rolling_summary = trim_summary_to_budget(
                    st, tokenizer, cfg.rolling_summary_max_tokens
                )
        verbatim_rows = store.fetch_chat_session_turns_after(session_id, covers_until_id)
        limit_msgs = cfg.session_max_turns * 2
        if len(verbatim_rows) > limit_msgs:
            verbatim_rows = verbatim_rows[-limit_msgs:]
    else:
        verbatim_rows = store.fetch_chat_session_turns_recent(
            session_id, cfg.session_max_turns * 2
        )

    messages = [
        {"role": str(r["role"]), "content": str(r["content"])} for r in verbatim_rows
    ]
    messages = trim_history_messages_to_budget(
        messages, tokenizer, cfg.session_max_history_tokens
    )
    return messages, rolling_summary


def persist_user_assistant_turns(
    store: SQLiteStore,
    cfg: MemoryConfig,
    session_id: str,
    run_id: str,
    user_text: str,
    assistant_text: str,
    tokenizer: TokenizerService,
) -> None:
    if not cfg.enabled:
        return
    tu = tokenizer.count_tokens(user_text)
    ta = tokenizer.count_tokens(assistant_text)
    store.append_chat_session_turn(session_id, run_id, "user", user_text, tu)
    store.append_chat_session_turn(session_id, run_id, "assistant", assistant_text, ta)
