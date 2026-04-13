"""
解析 agentskills.io 风格的 ``SKILL.md``（YAML frontmatter + Markdown 正文）。

见 https://agentskills.io/specification
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.registry.skill_registry import SkillManifest

try:
    import yaml  # type: ignore[import-not-found]
except ImportError:
    yaml = None  # type: ignore[assignment]


def _split_frontmatter(raw: str) -> tuple[str, str] | None:
    """返回 (frontmatter_yaml, body_markdown)；无合法 frontmatter 时返回 None。"""
    text = raw.lstrip("\ufeff")
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None
    i = 1
    fm_lines: list[str] = []
    while i < len(lines):
        if lines[i].strip() == "---":
            body = "".join(lines[i + 1 :])
            return "".join(fm_lines), body
        fm_lines.append(lines[i])
        i += 1
    return None


def read_skill_md_body(skill_md_path: Path) -> str:
    """仅读取 ``SKILL.md`` 中 frontmatter 之后的 Markdown 正文（不校验 YAML）。"""
    try:
        raw = skill_md_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    split = _split_frontmatter(raw)
    if split is None:
        return ""
    return split[1].strip()


def _parse_allowed_tools_line(s: str) -> list[str]:
    """
    解析规范中的 ``allowed-tools`` 空格分隔列表。
    ``Bash(git:*)`` 等形式取括号前的工具名前缀（OpenAgent 侧再映射到已注册工具名）。
    """
    out: list[str] = []
    for tok in s.split():
        t = tok.strip()
        if not t:
            continue
        if "(" in t:
            t = t.split("(", 1)[0].strip()
        if t:
            out.append(t)
    return out


def _metadata_str(meta: dict[str, Any], *keys: str) -> str | None:
    for k in keys:
        v = meta.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _parse_trigger_keywords(fm: dict[str, Any]) -> list[str]:
    md = fm.get("metadata")
    if not isinstance(md, dict):
        return []
    raw = _metadata_str(md, "trigger_keywords", "openagent_trigger_keywords")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    v = md.get("trigger_keywords_list")
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def _parse_enabled(fm: dict[str, Any]) -> bool:
    md = fm.get("metadata")
    if not isinstance(md, dict):
        return True
    v = md.get("openagent_enabled")
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "off")
    return True


def _parse_tags(fm: dict[str, Any]) -> list[str]:
    md = fm.get("metadata")
    if not isinstance(md, dict):
        return []
    raw = _metadata_str(md, "tags", "openagent_tags")
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return []


def _display_name(fm: dict[str, Any], skill_name: str) -> str:
    md = fm.get("metadata")
    if isinstance(md, dict):
        dn = _metadata_str(md, "display_name", "openagent_display_name")
        if dn:
            return dn
    return skill_name.replace("-", " ").title()


def parse_skill_md(
    skill_md_path: Path,
    *,
    expected_dir_name: str | None = None,
    warnings: list[str] | None = None,
    defer_body: bool = False,
) -> SkillManifest | None:
    """
    读取单个 ``SKILL.md`` 并转为 ``SkillManifest``。
    ``expected_dir_name`` 若给出且与 frontmatter ``name`` 不一致，则跳过并记录警告（符合规范：name 与目录名一致）。
    ``defer_body=True`` 时不把正文载入内存，仅设置 ``skill_md_path``，命中后再 ``resolve_prompt_addon()``。
    """
    if yaml is None:
        return None
    try:
        raw = skill_md_path.read_text(encoding="utf-8")
    except OSError as e:
        if warnings is not None:
            warnings.append(f"{skill_md_path}: read error: {e}")
        return None

    split = _split_frontmatter(raw)
    if split is None:
        if warnings is not None:
            warnings.append(f"{skill_md_path}: missing YAML frontmatter (---)")
        return None
    fm_raw, body = split
    try:
        fm = yaml.safe_load(fm_raw)
    except yaml.YAMLError as e:
        if warnings is not None:
            warnings.append(f"{skill_md_path}: invalid YAML frontmatter: {e}")
        return None
    if not isinstance(fm, dict):
        if warnings is not None:
            warnings.append(f"{skill_md_path}: frontmatter must be a mapping")
        return None

    name = fm.get("name")
    if not isinstance(name, str) or not name.strip():
        if warnings is not None:
            warnings.append(f"{skill_md_path}: missing required 'name' in frontmatter")
        return None
    name = name.strip()

    if expected_dir_name is not None and name != expected_dir_name:
        if warnings is not None:
            warnings.append(
                f"{skill_md_path}: frontmatter name '{name}' != directory '{expected_dir_name}' (skipped)"
            )
        return None

    desc = fm.get("description")
    description = desc.strip() if isinstance(desc, str) else ""

    allow_raw = fm.get("allowed-tools") or fm.get("allowed_tools")
    tools_allowlist: list[str] = []
    if isinstance(allow_raw, str) and allow_raw.strip():
        tools_allowlist = _parse_allowed_tools_line(allow_raw)
    elif isinstance(allow_raw, list):
        tools_allowlist = [str(x).strip() for x in allow_raw if str(x).strip()]

    if not _parse_enabled(fm):
        if warnings is not None:
            warnings.append(f"{skill_md_path}: skill '{name}' disabled via metadata.openagent_enabled")
        return None

    body_text = body.strip()
    if defer_body:
        return SkillManifest(
            skill_id=name,
            name=_display_name(fm, name),
            description=description,
            trigger_keywords=_parse_trigger_keywords(fm),
            tools_allowlist=tools_allowlist,
            prompt_addon="",
            skill_md_path=skill_md_path.resolve(),
            enabled=True,
            tags=_parse_tags(fm),
        )

    return SkillManifest(
        skill_id=name,
        name=_display_name(fm, name),
        description=description,
        trigger_keywords=_parse_trigger_keywords(fm),
        tools_allowlist=tools_allowlist,
        prompt_addon=body_text,
        skill_md_path=None,
        enabled=True,
        tags=_parse_tags(fm),
    )
