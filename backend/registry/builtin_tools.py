"""
内置工具实现：在 ``ToolGateway`` 中通过 ``register_handler`` 绑定。

联网搜索使用 DuckDuckGo Instant Answer API（无需 API Key；结果可能为空或受限）。
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.registry.tool_gateway import ToolGateway
from backend.registry.tool_registry import ToolRegistry


def web_search(query: str) -> dict[str, Any]:
    """
    使用 DuckDuckGo ``/`` instant answer JSON 接口拉取摘要与相关主题。

    参数名须与配置中 ``input_schema`` 一致（当前为 ``query``）。
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "empty_query", "results": []}

    params = urlencode(
        {
            "q": q,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
    )
    url = f"https://api.duckduckgo.com/?{params}"
    req = Request(url, headers={"User-Agent": "OpenAgent/0.1 (builtin web_search)"})

    try:
        with urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        return {"ok": False, "error": type(e).__name__, "detail": str(e), "results": []}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_json", "results": []}

    abstract = (data.get("AbstractText") or data.get("Abstract") or "").strip()
    abstract_url = (data.get("AbstractURL") or "").strip()
    heading = (data.get("Heading") or "").strip()

    snippets: list[dict[str, str]] = []
    if abstract:
        snippets.append(
            {
                "title": heading or q,
                "snippet": abstract,
                "url": abstract_url,
            }
        )

    related = data.get("RelatedTopics") or []
    for item in related[:8]:
        if isinstance(item, dict) and item.get("Text"):
            snippets.append(
                {
                    "title": item.get("Text", "")[:120],
                    "snippet": item.get("Text", ""),
                    "url": item.get("FirstURL") or "",
                }
            )
        elif isinstance(item, dict) and "Topics" in item:
            for sub in (item.get("Topics") or [])[:3]:
                if isinstance(sub, dict) and sub.get("Text"):
                    snippets.append(
                        {
                            "title": sub.get("Text", "")[:120],
                            "snippet": sub.get("Text", ""),
                            "url": sub.get("FirstURL") or "",
                        }
                    )

    return {
        "ok": True,
        "query": q,
        "heading": heading,
        "results": snippets,
    }


def register_builtin_handlers(gateway: ToolGateway, registry: ToolRegistry) -> None:
    """为配置中已启用的已知内置工具绑定 handler。"""
    mapping = {
        "web_search": web_search,
    }
    for name, fn in mapping.items():
        t = registry.get(name)
        if t is not None and t.enabled:
            gateway.register_handler(name, fn)
