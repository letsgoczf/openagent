from __future__ import annotations

import json
import re
from typing import Any

from backend.config_loader import MemoryConfig
from backend.kernel.budget import Budget
from backend.kernel.trace import TraceWriter
from backend.models.base import ChatResponse, LLMAdapter
from backend.models.tokenizer import TokenizerService


def _llm_text(raw: Any) -> str:
    if isinstance(raw, ChatResponse):
        return (raw.content or "").strip()
    if raw is None:
        return ""
    return str(raw).strip()


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    return t


def parse_fragments_json(raw: str) -> list[str]:
    """解析 LLM 输出的 JSON：``{\"fragments\": [...]}`` 或顶层数组。"""
    t = _strip_json_fence(raw)
    if not t:
        return []
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        arr = data.get("fragments")
        if not isinstance(arr, list):
            return []
    else:
        return []
    out: list[str] = []
    for x in arr:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def extract_fragments_via_llm(
    *,
    llm: LLMAdapter,
    budget: Budget,
    cfg: MemoryConfig,
    user_text: str,
    assistant_text: str,
    trace: TraceWriter | None,
) -> list[str]:
    """
    用 LLM 从单轮对话抽取可检索片段（JSON）；计入 budget；失败返回 []。
    """
    if not cfg.fragment_llm_extraction_enabled:
        return []
    if not budget.can_call_llm() or budget.wall_clock_exceeded():
        if trace:
            trace.emit(
                "memory_fragment_extract_llm",
                {"ok": False, "skipped": True, "reason": "budget"},
            )
        return []

    cap = cfg.fragments_extract_max
    user_prompt = (
        f"Extract at most {cap} short, self-contained memory snippets from this dialogue turn "
        "for later semantic retrieval. Each snippet should be a fact, preference, decision, or "
        "named entity the user might refer to later. Use the same language as the dialogue.\n\n"
        'Return ONLY valid JSON: {{"fragments": ["...", "..."]}}. No markdown, no commentary.\n\n'
        f"USER:\n{user_text.strip()}\n\nASSISTANT:\n{assistant_text.strip()}"
    )
    messages = [
        {
            "role": "system",
            "content": "You output only compact JSON for memory indexing.",
        },
        {"role": "user", "content": user_prompt},
    ]
    try:
        raw = llm.chat(
            messages,
            stream=False,
            max_tokens=cfg.fragment_llm_extraction_max_tokens,
        )
    except Exception as e:  # noqa: BLE001
        if trace:
            trace.emit(
                "memory_fragment_extract_llm",
                {"ok": False, "error": str(e)},
            )
        return []

    text = _llm_text(raw)
    frags = parse_fragments_json(text)
    frags = frags[:cap]
    trimmed: list[str] = []
    for f in frags:
        if len(f) > cfg.fragment_max_chars:
            f = f[: cfg.fragment_max_chars].rsplit(" ", 1)[0]
        if f.strip():
            trimmed.append(f.strip())

    budget.record_llm_call()
    if trace:
        trace.emit(
            "memory_fragment_extract_llm",
            {
                "ok": True,
                "count": len(trimmed),
                "raw_chars": len(text),
            },
        )
    return trimmed


def reconstruct_context_via_llm(
    *,
    llm: LLMAdapter,
    budget: Budget,
    cfg: MemoryConfig,
    query: str,
    template_blob: str,
    tokenizer: TokenizerService,
    trace: TraceWriter | None,
) -> str | None:
    """
    将检索到的片段列表融合为短上下文；成功返回正文，失败/跳过返回 None（调用方用模板）。
    """
    if not cfg.reconstruct_llm_enabled:
        return None
    if not template_blob.strip():
        return None
    if not budget.can_call_llm() or budget.wall_clock_exceeded():
        if trace:
            trace.emit(
                "memory_reconstruct_llm",
                {"ok": False, "skipped": True, "reason": "budget"},
            )
        return None

    user_prompt = (
        "You fuse retrieved memory snippets into a short coherent context that helps answer "
        "the user's question. Do not invent facts not present in the snippets. Do not mention "
        "chunk_id or document citations. Use the same language as the snippets.\n\n"
        f"QUESTION:\n{query.strip()}\n\n"
        f"RETRIEVED SNIPPETS:\n{template_blob.strip()}\n\n"
        "Output plain text only, 2–6 short sentences or one tight paragraph."
    )
    messages = [
        {"role": "system", "content": "You compress memory snippets into useful context."},
        {"role": "user", "content": user_prompt},
    ]
    try:
        raw = llm.chat(
            messages,
            stream=False,
            max_tokens=cfg.reconstruct_llm_max_tokens,
        )
    except Exception as e:  # noqa: BLE001
        if trace:
            trace.emit("memory_reconstruct_llm", {"ok": False, "error": str(e)})
        return None

    text = _llm_text(raw)
    if not text:
        if trace:
            trace.emit("memory_reconstruct_llm", {"ok": False, "reason": "empty_output"})
        return None

    budget.record_llm_call()
    if trace:
        trace.emit(
            "memory_reconstruct_llm",
            {
                "ok": True,
                "out_tokens": tokenizer.count_tokens(text),
            },
        )
    return text
