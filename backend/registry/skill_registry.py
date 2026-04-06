"""
Skills Registry：manifest 加载 + trigger 匹配 + prompt_addon 注入 + 工具白名单控制。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ImportError:
    yaml = None  # type: ignore[assignment]


@dataclass
class SkillManifest:
    """单个 Skill 的元数据定义。"""

    skill_id: str
    name: str
    description: str
    trigger_keywords: list[str] = field(default_factory=list)
    tools_allowlist: list[str] = field(default_factory=list)  # 该技能允许使用的工具
    prompt_addon: str = ""  # 触发时注入到 system prompt 的附加内容
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


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

    def get_merged_allowlist(self, query: str) -> list[str] | None:
        """
        返回所有匹配 skill 的工具白名单并集。
        如果任一 skill 有 allowlist，则只允许这些工具的并集；否则返回 None（不限制）。
        """
        matched = self.match_skills(query)
        if not matched:
            return None

        merged: set[str] = set()
        has_allowlist = False
        for skill in matched:
            if skill.tools_allowlist:
                has_allowlist = True
                merged.update(skill.tools_allowlist)

        return list(merged) if has_allowlist else None

    def get_prompt_addons(self, query: str) -> list[str]:
        """返回所有匹配 skill 的 prompt_addon。"""
        return [s.prompt_addon for s in self.match_skills(query) if s.prompt_addon]

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._skills.get(skill_id)

    def list_enabled(self) -> list[SkillManifest]:
        return [s for s in self._skills.values() if s.enabled]
