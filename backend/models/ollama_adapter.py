from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import ollama
from ollama import ResponseError

from backend.models.base import ChatResponse, LLMAdapter, StreamPart
from backend.models.ollama_client_util import ollama_httpx_kwargs


class OllamaAdapter(LLMAdapter):
    def __init__(
        self,
        model_id: str,
        *,
        base_url: str | None = None,
        think: bool | str | None = None,
    ) -> None:
        host = base_url or "http://127.0.0.1:11434"
        self._client = ollama.Client(host=host, **ollama_httpx_kwargs(host))
        self._host = host
        self._model = model_id
        self._think = think

    def _ollama_502_hint(self) -> str:
        m = self._model
        if ":cloud" in m or m.endswith("-cloud"):
            return (
                "当前 model 为 Ollama Cloud（名称含 `:cloud` 或以 `-cloud` 结尾），需 signin + 网络可达 ollama.com；"
                "若 CLI 正常而脚本仍 502，请查环境变量 HTTP_PROXY/HTTPS_PROXY，或对 127.0.0.1 设置 NO_PROXY。"
            )
        return (
            "本地 GGUF 仍 502 时，常见原因是 Python/httpx 走了系统代理（CLI 未走）。"
            f"可取消代理后重试，或 export NO_PROXY=127.0.0.1,localhost；并确认 "
            f"`curl -s {self._host}/api/tags` 与 `ollama run {self._model}` 正常。"
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse | Iterator[StreamPart]:
        options: dict[str, Any] = {}
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": stream,
        }
        if options:
            kwargs["options"] = options
        if tools:
            kwargs["tools"] = tools
        if self._think is not None:
            kwargs["think"] = self._think

        if stream:
            return self._stream_gen(**kwargs)

        return self._sync_call(**kwargs)

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _sync_call(self, **kwargs: Any) -> ChatResponse:
        """非流式：解析 content + thinking + tool_calls。"""
        try:
            resp = self._client.chat(**kwargs)
        except ResponseError as e:
            if e.status_code == 502:
                raise RuntimeError(f"{e!s}\n{self._ollama_502_hint()}") from e
            raise

        msg = resp.message
        if not msg:
            return ChatResponse(content="")

        thinking = msg.thinking or ""
        content = msg.content or ""

        # 解析 tool_calls
        raw_tool_calls = getattr(msg, "tool_calls", None) or []
        tool_calls = [
            {
                "id": f"tc_{i}",
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": _to_json_str(getattr(tc.function, "arguments", None)),
                },
            }
            for i, tc in enumerate(raw_tool_calls)
        ]

        return ChatResponse(content=content, tool_calls=tool_calls, thinking=thinking)

    def _stream_gen(self, **kwargs: Any) -> Iterator[StreamPart]:
        """流式：产出 (kind, delta)；若有 tool_calls，在结尾产出 tool_calls payload。"""
        accumulated: dict[str, Any] = {
            "content": [],
            "thinking": [],
            "tool_calls": [],  # 累积 tool_call chunks
        }

        s = self._client.chat(**kwargs)
        for part in s:
            part_msg = part.message
            if not part_msg:
                continue

            if part_msg.thinking:
                accumulated["thinking"].append(part_msg.thinking)
                yield ("thinking", part_msg.thinking)

            if part_msg.content:
                accumulated["content"].append(part_msg.content)
                yield ("content", part_msg.content)

            # Ollama 流式 tool_calls：每个 chunk 可能有 tool_calls
            part_tc = getattr(part_msg, "tool_calls", None) or []
            for tc in part_tc:
                fn = getattr(tc, "function", None)
                if fn:
                    accumulated["tool_calls"].append(
                        {
                            "name": getattr(fn, "name", ""),
                            "arguments": _to_json_str(getattr(fn, "arguments", None)),
                        }
                    )

        # 流结束后，若有 tool_calls，产出一个 special payload
        if accumulated["tool_calls"]:
            yield ("tool_calls", _build_tool_calls_payload(accumulated["tool_calls"]))


def _to_json_str(args: Any) -> str:
    """Ollama function.arguments 可能是 dict 或 str；统一转 JSON 字符串。"""
    if isinstance(args, str):
        return args
    if isinstance(args, dict):
        return json.dumps(args, ensure_ascii=False)
    return str(args) if args is not None else "{}"


def _build_tool_calls_payload(entries: list[dict[str, str]]) -> list[dict[str, Any]]:
    """将累积的 tool_call 片段合并为 OpenAI 风格结构。"""
    result: list[dict[str, Any]] = []
    for i, entry in enumerate(entries):
        result.append(
            {
                "id": f"tc_{i}",
                "type": "function",
                "function": {
                    "name": entry["name"],
                    "arguments": entry["arguments"],
                },
            }
        )
    return result
