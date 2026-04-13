from __future__ import annotations

import re


def extract_fragments_from_turn(
    user: str,
    assistant: str,
    *,
    max_frags: int,
    max_chars: int,
) -> list[str]:
    """
    规则抽取 Phase C 片段：用户整句 + 助手回答按段/句切分。
    不做 LLM 抽取，避免额外预算；后续可换为 ``fragment_llm_enabled``。
    """
    out: list[str] = []
    u = user.strip()
    if len(u) >= 8:
        out.append(u[:max_chars])

    a = assistant.strip()
    if len(a) < 12:
        return _dedupe_cap(out, max_frags)

    parts = re.split(r"\n\s*\n+", a)
    if len(parts) <= 1:
        parts = re.split(r"(?<=[.!?。！？])\s+", a)

    for p in parts:
        p = p.strip()
        if len(p) < 16:
            continue
        if len(p) > max_chars:
            cut = p[:max_chars]
            sp = cut.rfind(" ")
            p = cut if sp < 12 else cut[:sp]
        if p and p not in out:
            out.append(p)
        if len(out) >= max_frags:
            break

    return _dedupe_cap(out, max_frags)


def _dedupe_cap(items: list[str], max_frags: int) -> list[str]:
    seen: set[str] = set()
    res: list[str] = []
    for x in items:
        k = x.strip()
        if not k or k in seen:
            continue
        seen.add(k)
        res.append(k)
        if len(res) >= max_frags:
            break
    return res
