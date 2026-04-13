from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.config_loader import OpenAgentSettings, resolve_repo_relative_path

_AGENT_MD = re.compile(r"^(.+)\.agent\.md$")


@dataclass(frozen=True)
class AgentTemplateEntry:
    """`prompts/<id>.agent.md` 的一条目录项，供顶层规划 LLM 选择。"""

    id: str
    path: Path
    blurb: str


def _blurb_from_markdown(text: str, *, max_len: int) -> str:
    head = text[:12000]
    m = re.search(r'"prompt_goal"\s*:\s*"((?:[^"\\]|\\.)*)"', head)
    if m:
        return m.group(1).strip()[:max_len]
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("# ") and len(s) > 2:
            return s[2:].strip()[:max_len]
    one = " ".join(text.split())[:max_len]
    return one


def discover_agent_templates(
    *,
    prompts_dir: Path | None = None,
    settings: OpenAgentSettings | None = None,
    blurb_max_len: int = 220,
) -> list[AgentTemplateEntry]:
    """
    扫描仓库下 ``prompts_dir`` 中所有 ``*.agent.md``，生成规划用目录。
    """
    cfg = settings
    rel = "prompts"
    if cfg is not None:
        rel = cfg.prompt_management.prompts_dir
    root = prompts_dir
    if root is None:
        root = resolve_repo_relative_path(rel)
    if not root.is_dir():
        return []

    out: list[AgentTemplateEntry] = []
    for p in sorted(root.glob("*.agent.md")):
        m = _AGENT_MD.match(p.name)
        if not m:
            continue
        tid = m.group(1)
        try:
            body = p.read_text(encoding="utf-8")
        except OSError:
            continue
        out.append(
            AgentTemplateEntry(
                id=tid,
                path=p.resolve(),
                blurb=_blurb_from_markdown(body, max_len=blurb_max_len),
            )
        )
    return out


def format_catalog_for_planner(entries: list[AgentTemplateEntry]) -> str:
    lines: list[str] = []
    for e in entries:
        lines.append(f"- {e.id}: {e.blurb}")
    return "\n".join(lines) if lines else "(no templates)"


def load_template_bodies(
    template_ids: list[str],
    *,
    entries: list[AgentTemplateEntry] | None = None,
    prompts_dir: Path | None = None,
    settings: OpenAgentSettings | None = None,
    max_chars_per_template: int = 12000,
) -> list[str]:
    """
    按 id 读取模板全文（截断到 ``max_chars_per_template``），顺序与 ``template_ids`` 一致；未知 id 跳过。
    """
    if not template_ids:
        return []
    catalog = entries
    if catalog is None:
        catalog = discover_agent_templates(prompts_dir=prompts_dir, settings=settings)
    by_id = {e.id: e for e in catalog}
    blocks: list[str] = []
    for tid in template_ids:
        e = by_id.get(tid)
        if e is None or not e.path.is_file():
            continue
        try:
            raw = e.path.read_text(encoding="utf-8")
        except OSError:
            continue
        if len(raw) > max_chars_per_template:
            raw = raw[:max_chars_per_template] + "\n\n…(truncated)"
        blocks.append(f"### Agent template: {tid}\n\n{raw}")
    return blocks


