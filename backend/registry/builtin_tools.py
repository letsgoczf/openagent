"""
内置工具实现：在 ``ToolGateway`` 中通过 ``register_handler`` 绑定。

联网搜索使用 DuckDuckGo Instant Answer API（无需 API Key；结果可能为空或受限）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config_loader import OpenAgentSettings, resolve_repo_relative_path
from backend.registry.tool_gateway import ToolGateway
from backend.registry.tool_registry import ToolRegistry

_SKILL_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_READ_SKILL_MAX_BYTES = 512_000
_READ_SKILL_MAX_CHARS = 120_000


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


def read_skill_reference_file(
    skill_id: str,
    relative_path: str,
    *,
    skills_root: Path,
) -> dict[str, Any]:
    """
    只读 ``skills_root/<skill_id>/`` 下 ``references/`` 或 ``assets/`` 内的文本文件（防路径穿越）。
    供 Agent Skills 包内渐进式披露 L3 使用。
    """
    sid = (skill_id or "").strip()
    if not sid or _SKILL_ID_RE.fullmatch(sid) is None:
        return {"ok": False, "error": "invalid_skill_id"}

    rel = (relative_path or "").strip().replace("\\", "/")
    parts = [p for p in rel.split("/") if p]
    if not rel or rel.startswith("/") or any(p == ".." for p in parts):
        return {"ok": False, "error": "invalid_relative_path"}

    rel_lower = rel.lower()
    if not (rel_lower.startswith("references/") or rel_lower.startswith("assets/")):
        return {"ok": False, "error": "path_must_start_with_references_or_assets"}

    base = (skills_root / sid).resolve()
    if not base.is_dir():
        return {"ok": False, "error": "skill_directory_not_found"}

    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        return {"ok": False, "error": "path_escape"}

    if not target.is_file():
        return {"ok": False, "error": "not_a_file"}

    try:
        nbytes = target.stat().st_size
    except OSError as e:
        return {"ok": False, "error": "stat_failed", "detail": str(e)}
    if nbytes > _READ_SKILL_MAX_BYTES:
        return {
            "ok": False,
            "error": "file_too_large",
            "max_bytes": _READ_SKILL_MAX_BYTES,
        }

    try:
        raw = target.read_bytes()
    except OSError as e:
        return {"ok": False, "error": "read_failed", "detail": str(e)}

    text = raw.decode("utf-8", errors="replace")
    if len(text) > _READ_SKILL_MAX_CHARS:
        text = text[:_READ_SKILL_MAX_CHARS] + "\n…(truncated)"

    return {
        "ok": True,
        "skill_id": sid,
        "relative_path": rel,
        "chars": len(text),
        "content": text,
    }


def register_builtin_handlers(
    gateway: ToolGateway,
    registry: ToolRegistry,
    settings: OpenAgentSettings | None = None,
) -> None:
    """为配置中已启用的已知内置工具绑定 handler。"""
    mapping: dict[str, Callable[..., Any]] = {
        "web_search": web_search,
    }
    if settings is not None:
        root = resolve_repo_relative_path(str(settings.skills_bundle.skills_dir))

        def read_skill_reference(skill_id: str, relative_path: str) -> dict[str, Any]:
            return read_skill_reference_file(skill_id, relative_path, skills_root=root)

        mapping["read_skill_reference"] = read_skill_reference

    for name, fn in mapping.items():
        t = registry.get(name)
        if t is not None and t.enabled:
            gateway.register_handler(name, fn)
