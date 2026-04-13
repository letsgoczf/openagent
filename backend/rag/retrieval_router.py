from __future__ import annotations

import json
import re
from typing import Any

from backend.kernel.budget import Budget
from backend.kernel.trace import TraceWriter
from backend.models.base import ChatResponse, LLMAdapter

_ROUTER_SYSTEM = """You are a retrieval router for an assistant that may search an internal knowledge base (user-uploaded documents).

Decide if this specific user message requires searching those documents to answer well, or if answering without document search is appropriate.

Set need_retrieval=true when the user asks for facts, quotes, policies, procedures, numbers, or wording likely only in their uploaded files, or explicitly refers to documents/materials/attachments/PDFs/the knowledge base.

Set need_retrieval=false for ALL of the following (do not search the document store):
- Meta questions about THIS assistant/system: what tools/skills/capabilities/plugins/models it has, how to use the product UI, "what can you do", "list your tools", "你会什么", "有哪些工具/技能", "内置能力".
- Greetings, thanks, chit-chat, opinions, creative writing, generic coding or math with no document context.
- Questions that are clearly about public/common knowledge and not about the user's uploads.

If the user mixes "what tools do you have" with "according to my uploaded file", still set need_retrieval=true because the file part matters.

Reply with ONLY valid JSON: {"need_retrieval": true} or {"need_retrieval": false}
No markdown fences, no other text."""

# 用户明确在问「上传材料里的 …」时不要短路跳过
_DOC_SCOPE_HINT = re.compile(
    r"(文档|文件|上传|材料|附件|pdf|资料|知识库|这份|该文件|库里|表里|书中|第\s*\d+\s*(页|章))",
    re.I,
)

# 明显的「问助手自身工具/技能/能力」——不耗路由器 LLM，直接不检索
_META_SKIP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(你|您|系统|助手|agent|当前|内置|本系统).{0,24}(工具|技能|能力|插件|function\s*calling)",
        re.I,
    ),
    re.compile(
        r"(工具|技能|能力|插件).{0,16}(有哪些|都有什么|是什么|列出|列举|可用|能用|支持|会哪些)",
        re.I,
    ),
    re.compile(r"(会什么|能做什么|能干什么|可以做什么|有什么功能)", re.I),
    re.compile(
        r"\b(what|which)\s+tools?\s+(do\s+you|can\s+you|are\s+available|do\s+i\s+have)\b",
        re.I,
    ),
    re.compile(
        r"\b(list|show)\s+(your\s+|the\s+|my\s+)?(tools|skills|capabilities|functions)\b",
        re.I,
    ),
)


def meta_query_skip_retrieval(query: str) -> bool:
    """对明显的系统/助手元问题返回 True，表示应跳过文档检索（不调用路由器 LLM）。"""
    q = (query or "").strip()
    if len(q) < 4 or _DOC_SCOPE_HINT.search(q):
        return False
    return any(p.search(q) for p in _META_SKIP_PATTERNS)


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    return t


def _bool_from_need_retrieval_value(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if v in (0, 1):
        return bool(v)
    return None


def _extract_need_retrieval_bool(text: str) -> bool | None:
    """从一段文本中解析 need_retrieval；支持整段 JSON 或夹杂其它文字时的最小 JSON 子串。"""
    t = _strip_json_fence(text.strip())
    if not t:
        return None
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        got = _bool_from_need_retrieval_value(data.get("need_retrieval"))
        if got is not None:
            return got
    m = re.search(r'\{\s*"need_retrieval"\s*:\s*(true|false)\s*\}', t, re.I)
    if m:
        return m.group(1).lower() == "true"
    return None


def _parse_need_retrieval(raw: Any) -> bool | None:
    if isinstance(raw, ChatResponse):
        for piece in (raw.content or "", raw.thinking or ""):
            got = _extract_need_retrieval_bool(piece)
            if got is not None:
                return got
        combined = f"{raw.content or ''}\n{raw.thinking or ''}"
        return _extract_need_retrieval_bool(combined)
    if raw is None:
        return None
    return _extract_need_retrieval_bool(str(raw))


def llm_decides_need_retrieval(
    *,
    query: str,
    llm: LLMAdapter,
    budget: Budget,
    trace: TraceWriter,
    max_tokens: int,
    fail_open: bool = True,
) -> bool:
    """
    返回 True 表示应执行 RAG。

    ``fail_open``：解析失败或 LLM 异常时 true=仍检索（宽松），false=不检索（收紧）。
    预算耗尽无法调用路由器时仍返回 True（与主对话预算分离时的保守行为）。
    """
    if not budget.can_call_llm() or budget.wall_clock_exceeded():
        if trace:
            trace.emit(
                "retrieval_router",
                {
                    "need_retrieval": True,
                    "skipped": True,
                    "reason": "budget",
                },
            )
        return True

    q = query.strip()[:3000]
    if meta_query_skip_retrieval(q):
        if trace:
            trace.emit(
                "retrieval_router",
                {
                    "need_retrieval": False,
                    "skipped": True,
                    "reason": "meta_query_heuristic",
                },
            )
        return False

    messages = [
        {"role": "system", "content": _ROUTER_SYSTEM},
        {"role": "user", "content": f"USER_MESSAGE:\n{q}"},
    ]
    try:
        raw = llm.chat(messages, stream=False, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001
        need = fail_open
        if trace:
            trace.emit(
                "retrieval_router",
                {
                    "need_retrieval": need,
                    "parse_ok": False,
                    "error": str(e),
                    "fail_open": fail_open,
                },
            )
        return need

    parsed = _parse_need_retrieval(raw)
    if parsed is None:
        preview = ""
        if isinstance(raw, ChatResponse):
            preview = ((raw.content or "") + (raw.thinking or ""))[:240]
        else:
            preview = str(raw)[:240]
        need = fail_open
        if trace:
            trace.emit(
                "retrieval_router",
                {
                    "need_retrieval": need,
                    "parse_ok": False,
                    "raw_preview": preview,
                    "fail_open": fail_open,
                },
            )
        return need

    budget.record_llm_call()
    if trace:
        trace.emit(
            "retrieval_router",
            {
                "need_retrieval": parsed,
                "parse_ok": True,
            },
        )
    return parsed
