"""
基于 L1 技能目录（name + description）的 LLM 路由，与关键词匹配组合。
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.config_loader import OpenAgentSettings
from backend.kernel.budget import Budget
from backend.kernel.trace import TraceWriter
from backend.models.base import ChatResponse, LLMAdapter
from backend.registry.skill_registry import SkillManifest, SkillRegistry

_ROUTER_SYSTEM = """You are a skill router for OpenAgent.
Each line is one skill: skill_id — name — description (when to use it).

Pick skill_id values that clearly apply to the user's current message. Use ONLY ids from the list below. If none apply, return an empty array.

Reply with ONLY valid JSON (no markdown fences): {{"skill_ids":["id1","id2"]}}
At most {max_n} ids. Fewer is better when unsure."""


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t).strip()
    return t


def _parse_skill_ids_json(text: str) -> list[str] | None:
    t = _strip_json_fence(text.strip())
    if not t:
        return None
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("skill_ids")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    for x in raw:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
    return out


def _raw_from_llm(raw: Any) -> str:
    if isinstance(raw, ChatResponse):
        return (raw.content or "") + ("\n" + (raw.thinking or "") if raw.thinking else "")
    return str(raw)


def _format_l1_catalog(l1: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for e in l1:
        sid = e.get("skill_id", "")
        name = e.get("name", "")
        desc = (e.get("description") or "").replace("\n", " ").strip()
        lines.append(f"- {sid} — {name} — {desc}")
    return "\n".join(lines) if lines else "(no skills)"


def _dedupe_skills(order: list[SkillManifest]) -> list[SkillManifest]:
    seen: set[str] = set()
    out: list[SkillManifest] = []
    for s in order:
        if s.skill_id in seen:
            continue
        seen.add(s.skill_id)
        out.append(s)
    return out


def llm_pick_skill_ids(
    *,
    query: str,
    l1_index: list[dict[str, str]],
    allowed_ids: set[str],
    llm: LLMAdapter,
    budget: Budget,
    trace: TraceWriter | None,
    max_tokens: int,
    max_skills_selected: int,
) -> list[str]:
    """一次短 LLM 调用，返回合法的 skill_id 列表（已过滤到 allowed_ids）。"""
    if not allowed_ids or not budget.can_call_llm() or budget.wall_clock_exceeded():
        if trace:
            trace.emit(
                "skill_router",
                {"skipped": True, "reason": "empty_catalog_or_budget"},
            )
        return []

    max_n = max(1, min(max_skills_selected, len(allowed_ids)))
    system = _ROUTER_SYSTEM.format(max_n=max_n)
    user = (
        "SKILLS:\n"
        + _format_l1_catalog(l1_index)
        + "\n\nUSER_MESSAGE:\n"
        + query.strip()[:4000]
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    try:
        raw = llm.chat(messages, stream=False, max_tokens=max_tokens)
    except Exception as e:  # noqa: BLE001
        if trace:
            trace.emit(
                "skill_router",
                {"parse_ok": False, "error": str(e)},
            )
        return []

    parsed = _parse_skill_ids_json(_raw_from_llm(raw))
    if parsed is None:
        preview = _raw_from_llm(raw)[:240]
        if trace:
            trace.emit(
                "skill_router",
                {"parse_ok": False, "raw_preview": preview},
            )
        return []

    filtered = [i for i in parsed if i in allowed_ids][:max_n]
    budget.record_llm_call()
    if trace:
        trace.emit(
            "skill_router",
            {
                "parse_ok": True,
                "skill_ids": filtered,
            },
        )
    return filtered


def resolve_matched_skills(
    skill_registry: SkillRegistry,
    query: str,
    *,
    llm: LLMAdapter | None,
    budget: Budget,
    trace: TraceWriter | None,
    settings: OpenAgentSettings,
) -> list[SkillManifest]:
    """
    解析本回合应激活的技能：关键词匹配 ± LLM 路由（由 ``skill_router`` 配置决定）。
    """
    kw_matched = skill_registry.match_skills(query)
    sr = getattr(settings, "skill_router", None)
    if sr is None or getattr(sr, "enabled", False) is not True:
        return kw_matched

    if llm is None:
        return kw_matched

    l1 = skill_registry.list_l1_index()
    allowed_ids = {e["skill_id"] for e in l1 if e.get("skill_id")}
    if not allowed_ids:
        return kw_matched

    mode = getattr(sr, "mode", "hybrid")
    if not isinstance(mode, str):
        mode = "hybrid"
    mode = mode.lower()
    if mode not in ("hybrid", "llm_only"):
        mode = "hybrid"

    max_tokens = getattr(sr, "max_tokens", 256)
    if not isinstance(max_tokens, int):
        max_tokens = 256
    max_pick = getattr(sr, "max_skills_selected", 4)
    if not isinstance(max_pick, int):
        max_pick = 4

    picked_ids = llm_pick_skill_ids(
        query=query,
        l1_index=l1,
        allowed_ids=allowed_ids,
        llm=llm,
        budget=budget,
        trace=trace,
        max_tokens=max_tokens,
        max_skills_selected=max_pick,
    )
    llm_matched: list[SkillManifest] = []
    for sid in picked_ids:
        m = skill_registry.get(sid)
        if m is not None and m.enabled:
            llm_matched.append(m)

    if mode == "llm_only":
        return llm_matched if llm_matched else kw_matched

    return _dedupe_skills([*kw_matched, *llm_matched])
