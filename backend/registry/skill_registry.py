"""
Skills Registry：manifest 加载 + trigger 匹配 + prompt_addon 注入 + 工具白名单控制。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ImportError:
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class SkillManifest:
    """单个 Skill 的元数据定义。"""

    skill_id: str
    name: str
    description: str
    trigger_keywords: list[str] = field(default_factory=list)
    tools_allowlist: list[str] = field(default_factory=list)  # 该技能允许使用的工具
    prompt_addon: str = ""  # 内联附加内容；若为空且 ``skill_md_path`` 存在则按需读盘
    skill_md_path: Path | None = None  # 磁盘 SKILL.md；渐进式披露 L2
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    _cached_body: str | None = field(default=None, init=False, repr=False)

    def resolve_prompt_addon(self) -> str:
        """
        返回注入 system 的正文：优先 ``prompt_addon``；否则从 ``skill_md_path`` 读 Markdown body（仅首次读盘并缓存）。
        """
        if self.prompt_addon:
            return self.prompt_addon
        if self._cached_body is not None:
            return self._cached_body
        if self.skill_md_path is not None:
            from backend.registry.skill_md import read_skill_md_body

            self._cached_body = read_skill_md_body(self.skill_md_path)
        else:
            self._cached_body = ""
        return self._cached_body


class SkillRegistry:
    """
    技能注册表：
    - 加载 manifest 配置
    - 按 query 内容匹配触发的 skill（基于关键词）
    - 返回 tool_allowlist 供 ToolRegistry 使用
    - 返回 prompt_addon 注入到 prompt composer
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillManifest] = {}

    # ------------------------------------------------------------------ #
    # 注册
    # ------------------------------------------------------------------ #

    def register(self, skill: SkillManifest) -> None:
        self._skills[skill.skill_id] = skill

    def load_from_config(self, skills_config: list[dict[str, Any]]) -> None:
        """
        从配置批量加载。配置项格式：

        ```yaml
        skills:
          - skill_id: code_analyst
            name: "代码分析技能"
            description: "分析代码库"
            trigger_keywords: ["代码", "分析", "重构", "bug"]
            tools_allowlist: ["read_file", "search_codebase"]
            prompt_addon: "请使用结构化输出分析代码。"
            enabled: true
            tags: [code]
        ```
        """
        for item in skills_config:
            self.register(
                SkillManifest(
                    skill_id=item["skill_id"],
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    trigger_keywords=item.get("trigger_keywords", []),
                    tools_allowlist=item.get("tools_allowlist", []),
                    prompt_addon=item.get("prompt_addon", ""),
                    skill_md_path=None,
                    enabled=item.get("enabled", True),
                    tags=item.get("tags", []),
                )
            )

    def load_from_manifest_path(self, manifest_path: str) -> None:
        """从 YAML manifest 文件加载。"""
        if yaml is None:
            raise ImportError("PyYAML is required to load skill manifests")

        with open(manifest_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, list):
            self.load_from_config(data)
        elif isinstance(data, dict) and "skills" in data:
            self.load_from_config(data["skills"])

    def load_from_skills_directory(self, root: Path, *, defer_body: bool = True) -> list[str]:
        """
        从目录加载 agentskills.io 风格技能包：``root/<skill-name>/SKILL.md``。

        忽略以 ``.`` 或 ``_`` 开头的目录名；``name`` 与目录名不一致的条目跳过。
        ``defer_body=True``（默认）时仅缓存 frontmatter 与路径，命中后再读正文（渐进式披露 L2）。
        返回警告列表（便于测试与排障）；同时写入 logging。
        """
        from backend.registry.skill_md import parse_skill_md

        warnings: list[str] = []
        if not root.is_dir():
            return warnings

        for sub in sorted(root.iterdir()):
            if not sub.is_dir():
                continue
            if sub.name.startswith((".", "_")):
                continue
            skill_file = sub / "SKILL.md"
            if not skill_file.is_file():
                continue
            m = parse_skill_md(
                skill_file,
                expected_dir_name=sub.name,
                warnings=warnings,
                defer_body=defer_body,
            )
            if m is not None:
                self.register(m)

        for w in warnings:
            logger.warning("%s", w)
        return warnings

    def apply_tool_name_aliases(self, aliases: dict[str, str]) -> None:
        """按配置重写各技能的 ``tools_allowlist``（加载 YAML/磁盘完成后调用一次）。"""
        from backend.registry.skill_tools import normalize_tool_names

        if not aliases:
            return
        for skill in self._skills.values():
            if not skill.tools_allowlist:
                continue
            skill.tools_allowlist = normalize_tool_names(skill.tools_allowlist, aliases)

    # ------------------------------------------------------------------ #
    # 匹配与查询
    # ------------------------------------------------------------------ #

    def match_skills(self, query: str) -> list[SkillManifest]:
        """根据 query 内容匹配触发的 skill（关键词匹配）。"""
        query_lower = query.lower()
        matched: list[SkillManifest] = []
        for skill in self._skills.values():
            if not skill.enabled:
                continue
            for kw in skill.trigger_keywords:
                if kw.lower() in query_lower:
                    matched.append(skill)
                    break  # 一个关键词命中即可
        return matched

    @staticmethod
    def merged_allowlist_from_matches(matched: list[SkillManifest]) -> list[str] | None:
        """
        由已匹配技能列表合并工具白名单并集。
        若无一技能配置 allowlist，返回 None（不限制工具）。
        """
        if not matched:
            return None
        merged: set[str] = set()
        has_allowlist = False
        for skill in matched:
            if skill.tools_allowlist:
                has_allowlist = True
                merged.update(skill.tools_allowlist)
        return list(merged) if has_allowlist else None

    @staticmethod
    def prompt_addons_from_matches(matched: list[SkillManifest]) -> list[str]:
        """由已匹配技能列表收集注入正文（含按需读盘的 SKILL.md body）。"""
        out: list[str] = []
        for s in matched:
            block = s.resolve_prompt_addon()
            if block:
                out.append(block)
        return out

    def get_merged_allowlist(self, query: str) -> list[str] | None:
        """
        返回所有匹配 skill 的工具白名单并集。
        如果任一 skill 有 allowlist，则只允许这些工具的并集；否则返回 None（不限制）。
        """
        return self.merged_allowlist_from_matches(self.match_skills(query))

    def get_prompt_addons(self, query: str) -> list[str]:
        """返回所有匹配 skill 的注入正文（含按需从磁盘加载的 SKILL.md body）。"""
        return self.prompt_addons_from_matches(self.match_skills(query))

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._skills.get(skill_id)

    def list_enabled(self) -> list[SkillManifest]:
        return [s for s in self._skills.values() if s.enabled]

    def list_l1_index(self) -> list[dict[str, str]]:
        """
        渐进式披露 L1：仅 ``skill_id`` / ``name`` / ``description``。
        正文可能尚未加载（见 ``defer_body`` / ``resolve_prompt_addon``）。
        """
        out: list[dict[str, str]] = []
        for s in self._skills.values():
            if not s.enabled:
                continue
            out.append(
                {
                    "skill_id": s.skill_id,
                    "name": s.name,
                    "description": s.description,
                }
            )
        return out
