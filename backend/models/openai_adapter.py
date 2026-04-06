from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from openai import OpenAI

from backend.models.base import ChatResponse, LLMAdapter


class OpenAIAdapter(LLMAdapter):
    def __init__(
        self,
        model_id: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if api_key is not None:
            kwargs["api_key"] = api_key
        if base_url is not None:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model_id

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse | Iterator[str] | Iterator[StreamPart]:
        req: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": stream,
        }
        if temperature is not None:
            req["temperature"] = temperature
        if max_tokens is not None:
            req["max_tokens"] = max_tokens
        if tools:
            req["tools"] = tools

        if stream:

            def gen() -> Iterator[tuple[str, str]]:
                # Streaming：OpenAI 可能在 delta 中逐步输出 tool_calls。
                # 我们尽量累积 tool_calls 并在结束时吐出一个 ("tool_calls", json_str)。
                import json

                tool_calls_acc: dict[int, dict[str, Any]] = {}

                def _ensure_idx(idx: int) -> dict[str, Any]:
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": f"tc_{idx}",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    return tool_calls_acc[idx]

                for part in self._client.chat.completions.create(**req):
                    choice = part.choices[0]
                    delta = choice.delta

                    if getattr(delta, "content", None):
                        yield ("content", delta.content)

                    raw_tcs = getattr(delta, "tool_calls", None)
                    if raw_tcs:
                        for tc in raw_tcs:
                            idx = getattr(tc, "index", None)
                            if idx is None:
                                idx = 0
                            entry = _ensure_idx(int(idx))

                            tc_id = getattr(tc, "id", None)
                            if tc_id:
                                entry["id"] = tc_id

                            fn = getattr(tc, "function", None)
                            if fn:
                                fn_name = getattr(fn, "name", None)
                                if fn_name:
                                    entry["function"]["name"] = fn_name
                                fn_args = getattr(fn, "arguments", None)
                                if fn_args:
                                    entry["function"]["arguments"] += fn_args

                if tool_calls_acc:
                    ordered = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
                    tool_calls_payload = ordered
                    # ChatRunner 约定：tool_calls kind 的 chunk 可能是 str，需要可被 json.loads。
                    yield ("tool_calls", json.dumps(tool_calls_payload, ensure_ascii=False))

            return gen()

        resp = self._client.chat.completions.create(**req)
        msg = resp.choices[0].message
        raw_tool_calls = msg.tool_calls or []
        tool_calls = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in raw_tool_calls
        ]
        return ChatResponse(content=msg.content or "", tool_calls=tool_calls)
