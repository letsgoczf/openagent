from __future__ import annotations

import re
from collections.abc import Collection

# 与 prompts/<id>.agent.md 的常见文件名一致：字母数字、下划线、连字符
_MENTION = re.compile(r"@([a-zA-Z0-9][a-zA-Z0-9_-]*)")


def extract_forced_agent_templates(
    text: str,
    *,
    allowed_ids: Collection[str],
) -> tuple[list[str], str]:
    """
    从用户原文中提取 ``@<id>``（仅当 id 在目录中存在时视为 agent 模板）。

    返回 (按出现顺序去重后的 id 列表, 去掉这些 @mention 后的正文)。
    未知的 ``@词`` 保留在正文中（避免误伤邮箱等，且 id 不在目录时视为普通文本）。
    """
    raw = text.strip()
    allowed = frozenset(allowed_ids)
    found: list[str] = []
    seen: set[str] = set()
    spans: list[tuple[int, int]] = []

    for m in _MENTION.finditer(raw):
        tid = m.group(1)
        if tid not in allowed:
            continue
        spans.append((m.start(), m.end()))
        if tid not in seen:
            seen.add(tid)
            found.append(tid)

    if not spans:
        return [], raw

    spans.sort()
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    parts: list[str] = []
    last = 0
    for s, e in merged:
        parts.append(raw[last:s])
        last = e
    parts.append(raw[last:])
    cleaned = "".join(parts).strip()
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return found, cleaned
