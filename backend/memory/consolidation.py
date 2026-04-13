from __future__ import annotations

from typing import Any

from backend.config_loader import MemoryConfig
from backend.kernel.budget import Budget
from backend.kernel.trace import TraceWriter
from backend.models.base import ChatResponse, LLMAdapter
from backend.models.tokenizer import TokenizerService
from backend.storage.sqlite_store import SQLiteStore


def _format_turn_lines(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for r in rows:
        role = str(r.get("role", ""))
        content = str(r.get("content", "")).strip()
        if not content:
            continue
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def run_consolidation_if_needed(
    *,
    store: SQLiteStore,
    cfg: MemoryConfig,
    session_id: str,
    budget: Budget,
    llm: LLMAdapter,
    tokenizer: TokenizerService,
    trace: TraceWriter | None,
) -> None:
    """
    Phase B：当 verbatim（摘要尚未覆盖的尾部）超过 keep_recent_rounds 时，
    将超出部分折叠进滚动摘要（一次 LLM 调用，计入 budget）。
    """
    if not cfg.enabled or not cfg.consolidation_enabled:
        return

    n = store.count_chat_session_turns(session_id)
    pairs = n // 2
    if pairs < cfg.consolidate_after_turns:
        return

    row = store.get_chat_session_summary(session_id)
    covers_until_id = int(row["covers_until_id"]) if row else 0
    old_summary = (row["summary_text"] or "").strip() if row else ""

    verbatim = store.fetch_chat_session_turns_after(session_id, covers_until_id)
    keep_n = cfg.keep_recent_rounds * 2
    if len(verbatim) <= keep_n:
        return

    excess = len(verbatim) - keep_n
    to_fold = verbatim[:excess]
    if not to_fold:
        return

    if not budget.can_call_llm() or budget.wall_clock_exceeded():
        if trace:
            trace.emit(
                "memory_consolidate",
                {
                    "ok": False,
                    "skipped": True,
                    "reason": "budget",
                },
            )
        return

    dialogue = _format_turn_lines(to_fold)
    user_prompt = (
        "Merge OLD_SUMMARY with the following DIALOGUE excerpt into ONE concise rolling summary.\n"
        "Keep user goals, stated facts, decisions, and open questions. Use the same language as the dialogue.\n"
        "If OLD_SUMMARY is empty, summarize DIALOGUE only.\n\n"
        f"OLD_SUMMARY:\n{old_summary or '(empty)'}\n\n"
        f"DIALOGUE:\n{dialogue}\n\n"
        "Output only the merged summary text, no preamble."
    )
    messages = [
        {"role": "system", "content": "You compress chat logs into a dense factual summary."},
        {"role": "user", "content": user_prompt},
    ]
    try:
        raw = llm.chat(
            messages,
            stream=False,
            max_tokens=cfg.consolidation_max_output_tokens,
        )
    except Exception as e:  # noqa: BLE001
        if trace:
            trace.emit(
                "memory_consolidate",
                {"ok": False, "error": str(e)},
            )
        return

    if isinstance(raw, ChatResponse):
        text = (raw.content or "").strip()
    else:
        text = str(raw or "").strip()

    if not text:
        if trace:
            trace.emit("memory_consolidate", {"ok": False, "reason": "empty_llm_output"})
        return

    max_out = cfg.consolidation_max_output_tokens
    while tokenizer.count_tokens(text) > max_out and len(text) > 200:
        text = text[: int(len(text) * 0.85)].rstrip()

    new_covers = int(to_fold[-1]["id"])
    store.upsert_chat_session_summary(session_id, text, new_covers)
    budget.record_llm_call()

    if trace:
        trace.emit(
            "memory_consolidate",
            {
                "ok": True,
                "folded_messages": len(to_fold),
                "covers_until_id": new_covers,
                "summary_tokens": tokenizer.count_tokens(text),
            },
        )
