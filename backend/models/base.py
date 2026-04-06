from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

# 流式：优先 (kind, delta)，kind 为 content / thinking（Ollama）/ future tool_calls
StreamPart = tuple[str, str]


@dataclass
class ChatResponse:
    """
    单次 LLM 调用的完整响应（非流式返回此对象或纯文本）。
    - content: 助手回复正文
    - tool_calls: 工具调用列表（未调用时为空 list）
    - thinking: 推理过程（思考模型专用）
    """

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    thinking: str = ""


class LLMAdapter(ABC):
    """Unified chat/completions interface for OpenAI-compatible and Ollama backends."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str | ChatResponse | Iterator[str] | Iterator[StreamPart]:
        """
        非流式：``str``、``ChatResponse`` 或空字符串。
        流式：迭代 ``(kind, delta)``，kind 为 content / thinking / tool_calls（流尾）。
        """
