"""
Registry Service：统一接口供 Kernel / Runner 使用 Registry 资源。

职责：
- 初始化 ToolRegistry、ToolGateway、RagRegistry、SkillRegistry
- 从配置加载所有注册表
- 提供统一接口：check_tool、execute_tool、check_rag、match_skills 等
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.config_loader import OpenAgentSettings, load_config
from backend.kernel.blackboard import Blackboard
from backend.registry.rag_registry import RagCollection, RagRegistry
from backend.registry.skill_registry import SkillManifest, SkillRegistry
from backend.registry.builtin_tools import register_builtin_handlers
from backend.registry.tool_gateway import ToolCallResult, ToolGateway
from backend.registry.tool_registry import ToolDefinition, ToolRegistry


@dataclass
class RegistryService:
    """
    统一的 Registry 服务门面（Facade）。
    Kernel / Runner 只依赖此一个接口，无需直接访问各个 Registry。
    """

    tool_registry: ToolRegistry
    tool_gateway: ToolGateway
    rag_registry: RagRegistry
    skill_registry: SkillRegistry

    @classmethod
    def from_config(cls, settings: OpenAgentSettings | None = None) -> "RegistryService":
        """从配置初始化所有 Registry。"""
        cfg = settings or load_config()
        return build_registry_service(cfg)

    # ------------------------------------------------------------------ #
    # Tool 相关
    # ------------------------------------------------------------------ #

    def check_tool(self, tool_name: str) -> tuple[bool, str]:
        """
        检查工具是否允许调用（存在、启用、白名单）。
        返回 (是否允许, 原因)。
        """
        return self.tool_registry.is_tool_allowed(tool_name)

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """执行工具调用（含权限、校验、分发）。"""
        return self.tool_gateway.execute(name, arguments)

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """获取所有已启用工具的 JSON Schema（给 LLM 用）。"""
        return self.tool_registry.get_all_schemas()

    # ------------------------------------------------------------------ #
    # RAG 相关
    # ------------------------------------------------------------------ #

    def check_collection(self, collection_id: str) -> bool:
        """检查 RAG collection 是否允许访问。"""
        return self.rag_registry.is_collection_allowed(collection_id)

    def get_allowed_collections(self) -> list[RagCollection]:
        """获取所有可用的 RAG 集合。"""
        return self.rag_registry.list_enabled()

    # ------------------------------------------------------------------ #
    # Skills 相关
    # ------------------------------------------------------------------ #

    def match_skills_for_query(self, query: str) -> list[SkillManifest]:
        """根据 query 匹配触发技能。"""
        return self.skill_registry.match_skills(query)

    def get_tools_for_query(self, query: str) -> list[str] | None:
        """获取 query 对应技能允许的 tool 白名单并集。None = 不限制。"""
        return self.skill_registry.get_merged_allowlist(query)

    def get_prompt_addons_for_query(self, query: str) -> list[str]:
        """获取 query 对应技能的 prompt addon 列表。"""
        return self.skill_registry.get_prompt_addons(query)

    # ------------------------------------------------------------------ #
    # 配置
    # ------------------------------------------------------------------ #

    def set_allowlist_from_query(self, query: str) -> None:
        """根据匹配的 Skill 设置 tool 白名单。"""
        tools = self.get_tools_for_query(query)
        self.tool_registry.set_allowlist(tools)


# --------------------------------------------------------------------------#
# 工厂函数
# --------------------------------------------------------------------------#


def build_registry_service(settings: OpenAgentSettings) -> "RegistryService":
    """
    从配置构建所有 Registry，并绑定到 RegistryService。
    """
    # 1. Tool Registry
    tool_reg = ToolRegistry()
    tools_cfg = getattr(settings, "tools", None) or []
    # OpenAgentSettings.tools 可能是 Pydantic 模型列表（ToolItemConfig），也可能是 dict 列表（测试/外部注入）
    tools_cfg = [
        (t.model_dump() if hasattr(t, "model_dump") else t)  # pydantic v2
        for t in tools_cfg
    ]
    tool_reg.load_from_config(tools_cfg)

    # 2. Tool Gateway + 内置工具 handler（如 web_search）
    tool_gw = ToolGateway(tool_reg)
    register_builtin_handlers(tool_gw, tool_reg)

    # 3. RAG Registry
    rag_reg = RagRegistry()
    rag_cfg = getattr(settings.rag, "views", None) if hasattr(settings, "rag") else None
    if rag_cfg:
        rag_reg.load_from_config({"views": rag_cfg})
    else:
        # 即使配置没有显式 views，也注册默认的 collection
        coll_name = settings.storage.qdrant.collection_name
        rag_reg.register(
            RagCollection(
                collection_id=coll_name,
                description="Main document index",
                enabled=True,
            )
        )

    # 4. Skill Registry
    skill_reg = SkillRegistry()
    skills_cfg = getattr(settings, "skills", None) or []
    skills_cfg = [
        (s.model_dump() if hasattr(s, "model_dump") else s)
        for s in skills_cfg
    ]
    skill_reg.load_from_config(skills_cfg)

    return RegistryService(
        tool_registry=tool_reg,
        tool_gateway=tool_gw,
        rag_registry=rag_reg,
        skill_registry=skill_reg,
    )
