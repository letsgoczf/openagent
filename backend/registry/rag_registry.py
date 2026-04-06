"""
RAG Registry：collection + filter 策略管理。
控制 RAG 可访问的 collection_id 和过滤策略。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RagCollection:
    """单个 RAG 集合配置。"""

    collection_id: str
    description: str
    enabled: bool = True
    filter_policy: dict[str, Any] = field(default_factory=dict)  # {"version_scope": [...], "origin_types": [...]}
    tags: list[str] = field(default_factory=list)


class RagRegistry:
    """
    RAG 注册表：
    - 注册 / 查询 collection
    - 权限控制（只允许访问已注册的 collection）
    - 提供 filter_policy 供检索时应用
    """

    def __init__(self) -> None:
        self._collections: dict[str, RagCollection] = {}

    # ------------------------------------------------------------------ #
    # 注册
    # ------------------------------------------------------------------ #

    def register(self, collection: RagCollection) -> None:
        self._collections[collection.collection_id] = collection

    def load_from_config(self, rag_config: dict[str, Any]) -> None:
        """
        从配置加载。配置项格式：

        ```yaml
        rag:
          views:
            - collection_id: openagent_chunks
              description: "主文档索引"
              enabled: true
              tags: [documents]
        ```
        """
        views = rag_config.get("views", [])
        for item in views:
            self.register(
                RagCollection(
                    collection_id=item["collection_id"],
                    description=item.get("description", ""),
                    enabled=item.get("enabled", True),
                    filter_policy=item.get("filter_policy", {}),
                    tags=item.get("tags", []),
                )
            )

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get(self, collection_id: str) -> RagCollection | None:
        return self._collections.get(collection_id)

    def list_enabled(self) -> list[RagCollection]:
        return [c for c in self._collections.values() if c.enabled]

    def collection_ids(self) -> list[str]:
        return list(self._collections.keys())

    def is_collection_allowed(self, collection_id: str) -> bool:
        """仅允许访问注册且启用的 collection。"""
        c = self._collections.get(collection_id)
        if c is None:
            return False
        return c.enabled

    def get_allowed_ids(self) -> list[str]:
        """返回所有可用的 collection_id 列表。"""
        return [c.collection_id for c in self.list_enabled()]
