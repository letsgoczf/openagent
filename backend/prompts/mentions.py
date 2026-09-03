from __future__ import annotations

import re
from collections.abc import Collection

# 与 prompts/<id>.agent.md 的常见文件名一致：字母数字、下划线、连字符。
# 必须是独立 token，不能落在邮箱中间（user@incident.com）或 @id.domain 上。
_MENTION = re.compile(
    r"(?<![A-Za-z0-9._])@([a-zA-Z0-9][a-zA-Z0-9_-]*)(?!\.[A-Za-z])"
)


def extract_forced_agent_templates(
    text: str,
    *,
    allowed_ids: Collection[str],
) -> tuple[list[str], str]:
    """
    从用户原文中提取 ``@<id>``（仅当 id 在目录中存在时视为 agent 模板）。

    返回 (按出现顺序去重后的 id 列表, 去掉这些 @mention 后的正文)。
    未知的 ``@词`` 保留在正文中。邮箱（``alerts@incident.io``）即使 local/domain
    与目录 id 相同也不视为 mention，避免改写提问并污染 session memory。
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
