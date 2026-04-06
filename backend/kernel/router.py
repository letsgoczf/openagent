from __future__ import annotations

from typing import Any

from backend.config_loader import OpenAgentSettings, load_config


def route_query(
    query: str,
    *,
    settings: OpenAgentSettings | None = None,
) -> dict[str, Any]:
    """
    路由：默认 single；若开启 multi 且 query 以前缀触发，则进入顺序双智能体（analyst → synthesizer）。
    """
    cfg = settings or load_config()
    raw = query.strip()
    mq = cfg.orchestration.multi_agent

    if mq.enabled and mq.trigger_prefix and raw.startswith(mq.trigger_prefix):
        rest = raw[len(mq.trigger_prefix) :].strip()
        effective = rest if rest else raw
        return {
            "mode": "multi",
            "profiles": ["analyst", "synthesizer"],
            "query_preview": effective[:200],
            "effective_query": effective,
        }

    return {
        "mode": "single",
        "profiles": ["default"],
        "query_preview": raw[:200],
        "effective_query": raw,
    }
