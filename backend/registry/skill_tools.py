"""
技能侧工具名：与 Agent Skills ``allowed-tools`` 等外部名称对齐到 OpenAgent 已注册工具名。
"""

from __future__ import annotations

# 与常见 Agent Skills / Claude 模板兼容：用户一般无需在 YAML 里再抄一份映射。
DEFAULT_SKILL_TOOL_ALIASES: dict[str, str] = {
    "Read": "read_skill_reference",
    "WebSearch": "web_search",
}


def merge_skill_tool_aliases(user: dict[str, str] | None) -> dict[str, str]:
    """内置别名 + 用户 ``skills_bundle.tool_name_aliases``（同键时用户覆盖）。"""
    out = dict(DEFAULT_SKILL_TOOL_ALIASES)
    if user:
        for k, v in user.items():
            ks = str(k).strip()
            if not ks:
                continue
            out[ks] = str(v).strip() if isinstance(v, str) else str(v)
    return out


def normalize_tool_names(tokens: list[str], aliases: dict[str, str]) -> list[str]:
    """
    按 ``aliases`` 映射工具名（键不区分大小写）；映射目标为空字符串则丢弃该 token。
    未出现在表中的名称保持原样；结果去重且保序。
    """
    if not tokens:
        return []
    amap = {
        str(k).lower().strip(): str(v).strip()
        for k, v in (aliases or {}).items()
        if str(k).strip()
    }
    out: list[str] = []
    seen: set[str] = set()
    for raw in tokens:
        t = (raw or "").strip()
        if not t:
            continue
        mapped = amap.get(t.lower(), t)
        if not mapped:
            continue
        if mapped in seen:
            continue
        seen.add(mapped)
        out.append(mapped)
    return out
