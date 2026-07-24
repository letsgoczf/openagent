from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from backend.kernel.blackboard import Blackboard
from backend.kernel.budget import Budget
from backend.registry.tool_gateway import ToolCallResult, ToolGateway


class ToolGatewayStub:
    """
    P4 遗留：未注册工具时一律拒绝。
    P6+ 应使用 ``backend.registry.tool_gateway.ToolGateway``，本类保留以兼容旧代码。
    """

    def execute(self, name: str, arguments: dict[str, Any]) -> tuple[bool, str, Any]:
        return False, "tool_not_registered", {"tool": name, "note": "use ToolGateway instead"}


ToolGatewayLike = ToolGateway | ToolGatewayStub


def run_tool_loop_round(
    *,
    budget: Budget,
    blackboard: Blackboard,
    gateway: ToolGatewayLike,
    tool_calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    执行一轮 tool_calls（OpenAI 风格：id, function.name, function.arguments JSON 字符串）。
    成功或失败均写入 blackboard ``tool`` 命名空间。
    """
    if not tool_calls:
        return []

    if not budget.can_tool_round():
        blackboard.append("tool", "tool_budget_exhausted", {"count": len(tool_calls)})
        return []

    budget.record_tool_round()
    results: list[dict[str, Any]] = []
    for tc in tool_calls:
        fn = tc.get("function") or {}
        name = fn.get("name", "")
        raw_args = fn.get("arguments") or "{}"

        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            args = {}

        result, code, payload = _execute_via_gateway(gateway, name, args if isinstance(args, dict) else {})
        results.append({
            "tool_call_id": tc.get("id"),
            "tool": name,
            "result": result,
            "code": code,
            "payload": payload,
        })
        blackboard.append(
            "tool",
            "tool_call_finished" if result else "tool_call_failed",
            {"name": name, "code": code, "preview": str(payload)[:500]},
        )
    return results


def format_tool_results_for_llm(results: list[dict[str, Any]], *, max_chars: int = 8000) -> str:
    """将 tool 执行结果格式化为可回传给模型的用户消息正文。"""
    compact = [
        {
            "tool_call_id": r.get("tool_call_id"),
            "tool": r.get("tool"),
            "success": bool(r.get("result")),
            "code": r.get("code"),
            "payload": r.get("payload"),
        }
        for r in results
    ]
    return "Tool results:\n" + json.dumps(compact, ensure_ascii=False)[:max_chars]


def chat_until_no_tools(
    *,
    messages: list[dict[str, str]],
    budget: Budget,
    blackboard: Blackboard,
    llm_complete: Callable[[list[dict[str, str]]], tuple[str, list[dict[str, Any]] | None]],
    gateway: ToolGatewayLike | None = None,
    max_tool_rounds: int | None = None,
) -> str:
    """
    若 LLM 返回 tool_calls，则执行网关并把**实际工具结果**以 ``role=user`` 追加后继续生成。
    ``gateway=None`` 时默认使用 ToolGatewayStub（兼容 P4 行为）。
    """
    gw = gateway or ToolGatewayStub()
    cap = max_tool_rounds if max_tool_rounds is not None else budget.max_tool_rounds
    rounds = 0
    current = list(messages)
    text = ""

    while rounds <= cap:
        if not budget.can_call_llm():
            blackboard.append("tool", "llm_budget_exhausted", {})
            return text or ""
        text, tool_calls = llm_complete(current)
        budget.record_llm_call()

        if not tool_calls:
            return text

        tc_results = run_tool_loop_round(
            budget=budget,
            blackboard=blackboard,
            gateway=gw,
            tool_calls=tool_calls,
        )
        if not tc_results:
            # 工具预算耗尽：不再假装继续，直接返回本轮文本
            return text or ""
        current.append({"role": "assistant", "content": text or "(tool use)"})
        current.append(
            {
                "role": "user",
                "content": format_tool_results_for_llm(tc_results),
            }
        )
        rounds += 1

    blackboard.append("tool", "tool_round_cap", {"rounds": rounds})
    return text or ""


# --------------------------------------------------------------------------#
# 内部
# --------------------------------------------------------------------------#

def _execute_via_gateway(
    gateway: ToolGatewayLike,
    name: str,
    arguments: dict[str, Any],
) -> tuple[bool, str, Any]:
    """统一两种网关返回值类型。"""
    if isinstance(gateway, ToolGateway):
        tc_result: ToolCallResult = gateway.execute(name, arguments)
        return (
            tc_result.success,
            tc_result.error_code or "ok" if tc_result.success else tc_result.error_code,
            tc_result.output,
        )
    # Legacy: ToolGatewayStub 返回 (ok, code, payload)
    return gateway.execute(name, arguments)
