from __future__ import annotations

from unittest.mock import MagicMock

from backend.kernel.budget import Budget
from backend.models.base import ChatResponse, LLMAdapter
from backend.rag.retrieval_router import (
    llm_decides_need_retrieval,
    meta_query_skip_retrieval,
)


class _StubLLM(LLMAdapter):
    def __init__(self, content: str) -> None:
        self._content = content

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, object]] | None = None,
    ) -> ChatResponse:
        return ChatResponse(content=self._content)


def test_router_false_records_llm_call() -> None:
    llm = _StubLLM('{"need_retrieval": false}')
    b = Budget(max_llm_calls=8)
    trace = MagicMock()
    out = llm_decides_need_retrieval(
        query="你好",
        llm=llm,
        budget=b,
        trace=trace,
        max_tokens=80,
    )
    assert out is False
    assert b.llm_calls_used == 1
    trace.emit.assert_called()


def test_router_true_records_llm_call() -> None:
    llm = _StubLLM('{"need_retrieval": true}')
    b = Budget(max_llm_calls=8)
    out = llm_decides_need_retrieval(
        query="文档里怎么写的",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
    )
    assert out is True
    assert b.llm_calls_used == 1


def test_router_bad_json_fail_open_true_no_llm_record() -> None:
    llm = _StubLLM("not json")
    b = Budget(max_llm_calls=8)
    out = llm_decides_need_retrieval(
        query="x",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
        fail_open=True,
    )
    assert out is True
    assert b.llm_calls_used == 0


def test_router_bad_json_fail_closed_skips_retrieval() -> None:
    llm = _StubLLM("not json")
    b = Budget(max_llm_calls=8)
    out = llm_decides_need_retrieval(
        query="x",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
        fail_open=False,
    )
    assert out is False
    assert b.llm_calls_used == 0


def test_router_meta_tools_question_skips_llm() -> None:
    """与上传文档无关的「工具有哪些」类问题：启发式直接跳过检索，不耗路由器 LLM。"""
    llm = _StubLLM('{"need_retrieval": true}')
    b = Budget(max_llm_calls=8)
    out = llm_decides_need_retrieval(
        query="你现在可以用的工具、技能有哪些",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
    )
    assert out is False
    assert b.llm_calls_used == 0


def test_meta_heuristic_not_when_user_asks_uploaded_doc() -> None:
    assert meta_query_skip_retrieval("上传的文档里有哪些工具要求") is False


def test_meta_heuristic_tools_zh() -> None:
    assert meta_query_skip_retrieval("系统有哪些内置技能") is True
    assert meta_query_skip_retrieval("你会什么") is True


def test_meta_heuristic_tools_en() -> None:
    assert meta_query_skip_retrieval("What tools can you use?") is True


def test_router_budget_exhausted_skips_llm() -> None:
    llm = _StubLLM('{"need_retrieval": false}')
    b = Budget(max_llm_calls=0)
    out = llm_decides_need_retrieval(
        query="x",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
    )
    assert out is True
    assert b.llm_calls_used == 0


def test_router_json_in_fence() -> None:
    llm = _StubLLM('```json\n{"need_retrieval": false}\n```')
    b = Budget(max_llm_calls=8)
    out = llm_decides_need_retrieval(
        query="hi",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
    )
    assert out is False
    assert b.llm_calls_used == 1


def test_router_json_in_thinking_only() -> None:
    """思考模型可能把 JSON 放在 thinking 字段，content 为空。"""

    class _ThinkLLM(LLMAdapter):
        def chat(
            self,
            messages: list[dict[str, str]],
            *,
            stream: bool = False,
            temperature: float | None = None,
            max_tokens: int | None = None,
            tools: list[dict[str, object]] | None = None,
        ) -> ChatResponse:
            return ChatResponse(
                content="",
                thinking='{"need_retrieval": false}',
            )

    b = Budget(max_llm_calls=8)
    out = llm_decides_need_retrieval(
        query="你好",
        llm=_ThinkLLM(),
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
    )
    assert out is False
    assert b.llm_calls_used == 1


def test_router_embedded_json_in_prose() -> None:
    llm = _StubLLM('Sure. {"need_retrieval": false}')
    b = Budget(max_llm_calls=8)
    out = llm_decides_need_retrieval(
        query="hi",
        llm=llm,
        budget=b,
        trace=MagicMock(),
        max_tokens=80,
    )
    assert out is False
    assert b.llm_calls_used == 1
