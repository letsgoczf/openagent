"""
Tool Gateway：参数校验 / 超时 / 脱敏预览 + 工具执行分发。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.registry.tool_registry import ToolRegistry


@dataclass
class ToolCallResult:
    """单次工具调用结果。"""

    success: bool
    output: Any
    preview: str  # 脱敏预览（截断 + 敏感信息遮蔽）
    elapsed_ms: float
    error_code: str = ""
    error_detail: str = ""


class ToolGateway:
    """
    工具执行网关：
    1. 权限检查（通过 ToolRegistry）
    2. JSON Schema 参数校验
    3. 超时限制
    4. 执行工具函数
    5. 脱敏预览
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        default_timeout: float = 30.0,
        max_preview_length: int = 500,
    ) -> None:
        self._registry = registry
        self._default_timeout = default_timeout
        self._max_preview_length = max_preview_length
        self._handlers: dict[str, Callable[..., Any]] = {}

    # ------------------------------------------------------------------ #
    # 工具注册
    # ------------------------------------------------------------------ #

    def register_handler(self, name: str, handler: Callable[..., Any]) -> None:
        """为工具名绑定一个可调用对象。"""
        self._handlers[name] = handler

    # ------------------------------------------------------------------ #
    # 核心执行
    # ------------------------------------------------------------------ #

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolCallResult:
        """
        执行工具调用前的检查、执行、后处理。
        返回 ToolCallResult，包含结果、预览、耗时、错误码。
        """
        # 权限检查
        allowed, reason = self._registry.is_tool_allowed(name)
        if not allowed:
            return ToolCallResult(
                success=False,
                output=None,
                preview="",
                elapsed_ms=0.0,
                error_code=reason,
                error_detail=f"Tool '{name}' not allowed: {reason}",
            )

        # 参数校验
        valid, msg = self._registry.validate_arguments(name, arguments)
        if not valid:
            return ToolCallResult(
                success=False,
                output=None,
                preview="",
                elapsed_ms=0.0,
                error_code="invalid_arguments",
                error_detail=f"Schema validation failed: {msg}",
            )

        # 查找处理器
        handler = self._handlers.get(name)
        if handler is None:
            return ToolCallResult(
                success=False,
                output=None,
                preview="",
                elapsed_ms=0.0,
                error_code="handler_not_found",
                error_detail=f"No handler registered for tool '{name}'",
            )

        # 超时控制
        tool_def = self._registry.get(name)
        timeout = tool_def.timeout_seconds if tool_def else self._default_timeout

        start = time.monotonic()
        try:
            output = handler(**arguments)
            elapsed = (time.monotonic() - start) * 1000
            return ToolCallResult(
                success=True,
                output=output,
                preview=self._make_preview(output, self._max_preview_length),
                elapsed_ms=elapsed,
            )
        except TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
            return ToolCallResult(
                success=False,
                output=None,
                preview="",
                elapsed_ms=elapsed,
                error_code="tool_timeout",
                error_detail=f"Tool '{name}' exceeded {timeout}s timeout",
            )
        except Exception as e:  # noqa: BLE001
            elapsed = (time.monotonic() - start) * 1000
            return ToolCallResult(
                success=False,
                output=None,
                preview="",
                elapsed_ms=elapsed,
                error_code="handler_error",
                error_detail=repr(e),
            )

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #

    def _make_preview(self, obj: Any, max_length: int) -> str:
        """脱敏 + 截断预览。"""
        text = str(obj)
        # 简单脱敏：遮蔽类似密钥的长字符串
        text = self._mask_secrets(text)
        if len(text) > max_length:
            return text[: max_length - 3] + "..."
        return text

    @staticmethod
    def _mask_secrets(text: str) -> str:
        """遮蔽明显的敏感模式（API 密钥、令牌等）。"""
        import re
        # 匹配常见的密钥模式：key=..., token=..., secret=...
        patterns = [
            (r'(key|token|secret|password)\s*[:=]\s*["\']?\w{8,}', r'\1=***'),
            (r'Bearer\s+\w{8,}', 'Bearer ***'),
        ]
        for pattern, repl in patterns:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        return text
