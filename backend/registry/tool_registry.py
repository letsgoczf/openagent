"""
Tool Registry：从配置加载工具定义，JSON Schema 校验 + 白名单控制。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    """单个工具描述：名称、摘要、参数 JSON Schema、是否允许调用。"""

    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema
    enabled: bool = True
    timeout_seconds: float = 30.0
    tags: list[str] = field(default_factory=list)


class ToolRegistry:
    """
    工具注册表：
    - 从配置（dict 列表）构建 ToolDefinition 列表
    - 按名称查询
    - 白名单 / 黑名单校验
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._allowlist: set[str] | None = None  # None 表示无限制

    # ------------------------------------------------------------------ #
    # 注册
    # ------------------------------------------------------------------ #

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def load_from_config(self, tools_config: list[dict[str, Any]]) -> None:
        """
        从配置批量加载。配置项格式示例：

        ```yaml
        tools:
          - name: web_search
            description: "搜索互联网"
            input_schema:
              type: object
              properties:
                query: {type: string}
              required: [query]
            enabled: true
            timeout_seconds: 10
            tags: [search, external]
        ```
        """
        for item in tools_config:
            self.register(
                ToolDefinition(
                    name=item["name"],
                    description=item.get("description", ""),
                    input_schema=item.get("input_schema", {}),
                    enabled=item.get("enabled", True),
                    timeout_seconds=item.get("timeout_seconds", 30.0),
                    tags=item.get("tags", []),
                )
            )

    def set_allowlist(self, tools: list[str] | None) -> None:
        """设置白名单。None → 不限制（只要 enabled）。"""
        self._allowlist = set(tools) if tools else None

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_enabled(self) -> list[ToolDefinition]:
        return [t for t in self._tools.values() if t.enabled]

    def get_all_schemas(self) -> list[dict[str, Any]]:
        """返回所有已启用工具的 JSON Schema 列表（给 LLM 用）。"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in self.list_enabled()
        ]

    # ------------------------------------------------------------------ #
    # 访问控制
    # ------------------------------------------------------------------ #

    def is_tool_allowed(self, name: str) -> tuple[bool, str]:
        """
        检查调用权限：
        - 工具是否存在
        - 是否启用
        - 是否在白名单内（如果设置了白名单）

        返回 (是否允许, 拒绝原因)。
        """
        tool = self._tools.get(name)
        if tool is None:
            return False, "tool_not_found"
        if not tool.enabled:
            return False, "tool_disabled"
        if self._allowlist is not None and name not in self._allowlist:
            return False, "tool_not_in_allowlist"
        return True, ""

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        """校验参数是否符合 JSON Schema。"""
        tool = self._tools.get(name)
        if tool is None:
            return False, "tool_not_found"
        schema = tool.input_schema
        if not schema:
            return True, ""

        try:
            return self._json_schema_validate(schema, arguments)
        except Exception as e:
            return False, f"schema_validation_failed: {e}"

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    @staticmethod
    def _json_schema_validate(
        schema: dict[str, Any], arguments: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        轻量 JSON Schema 校验（零依赖）：仅校验 required + type。
        若项目后续引入 jsonschema 库，可替换为完整校验。
        """
        required = schema.get("required", [])
        for key in required:
            if key not in arguments:
                return False, f"missing required key '{key}'"

        props = schema.get("properties", {})
        for key, value in arguments.items():
            if key in props:
                expected_type = props[key].get("type")
                if expected_type and not _check_type(value, expected_type):
                    return False, f"type mismatch for '{key}': expected {expected_type}"
        return True, ""


def _check_type(value: Any, expected: str) -> bool:
    """基本类型校验。"""
    type_map = {
        "string": lambda v: isinstance(v, str),
        "number": lambda v: isinstance(v, (int, float)),
        "integer": lambda v: isinstance(v, int),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
        "null": lambda v: v is None,
    }
    checker = type_map.get(expected)
    if checker is None:
        return True  # 未知类型，跳过
    return checker(value)
