from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

from backend.config_loader import OpenAgentSettings, load_config
from backend.kernel.blackboard import Blackboard
from backend.kernel.budget import Budget
from backend.kernel.multi_chat import run_sequential_two_agent
from backend.kernel.router import route_query
from backend.kernel.run_context import RunContext
from backend.kernel.trace import TraceWriter
from backend.registry.service import RegistryService
from backend.runners.chat_runner import ChatRunResult, build_chat_runner


class KernelEngine:
    """
    Kernel 编排：RunContext + Trace + Router stub → ChatRunner + Tool Loop。
    P6 集成：RegistryService 用于 tool/Skill 白名单控制。
    """

    def __init__(
        self,
        settings: OpenAgentSettings | None = None,
        *,
        constitution_path: Path | None = None,
    ) -> None:
        self.settings = settings or load_config()
        self.constitution_path = constitution_path

    def run_chat(
        self,
        query: str,
        *,
        session_id: str | None = None,
        version_scope: list[str] | None = None,
        budget: Budget | None = None,
        trace_sink: Callable[[str, str, dict[str, object] | None, int, str], None] | None = None,
        stream: bool = False,
        stream_writer: Callable[[str, str], None] | None = None,
    ) -> ChatRunResult:
        run_id = str(uuid.uuid4())
        sid = session_id or str(uuid.uuid4())
        bud = budget or Budget()
        ctx = RunContext(run_id=run_id, session_id=sid, budget=bud)

        decision = route_query(query, settings=self.settings)
        effective_query = str(decision.get("effective_query") or query.strip())

        # 构建 Registry 并基于 Skill 匹配设置 tool 白名单（用 effective_query，multi 时不带触发前缀）
        registry = RegistryService.from_config(self.settings)
        registry.set_allowlist_from_query(effective_query)
        tool_schemas = registry.get_tool_schemas()
        matched_skills = registry.match_skills_for_query(effective_query)
        prompt_addons = registry.get_prompt_addons_for_query(effective_query)

        runner, sqlite, qdrant = build_chat_runner(
            self.settings,
            constitution_path=self.constitution_path,
            registry=registry,
            tool_schemas=tool_schemas,
        )
        trace = TraceWriter(sqlite, run_id, on_emit=trace_sink)
        bb = Blackboard()

        trace.emit("run_started", {"session_id": sid, "run_id": run_id})
        trace.emit("mode_selected", decision)
        bb.append("kernel", "mode_selected", decision)

        # 写 registry 相关信息到 trace
        if matched_skills:
            trace.emit(
                "skills_matched",
                {"skills": [s.skill_id for s in matched_skills]},
            )
        if prompt_addons:
            bb.append("kernel", "skill_addons", {"addons": prompt_addons})

        try:
            if decision.get("mode") == "multi":
                result = run_sequential_two_agent(
                    runner=runner,
                    ctx=ctx,
                    trace=trace,
                    blackboard=bb,
                    effective_query=effective_query,
                    version_scope=version_scope,
                    stream=stream,
                    stream_writer=stream_writer,
                    prompt_addons=prompt_addons,
                )
            else:
                result = runner.run(
                    ctx,
                    effective_query,
                    trace,
                    bb,
                    version_scope=version_scope,
                    stream=stream,
                    stream_writer=stream_writer,
                    prompt_addons=prompt_addons,
                )
        finally:
            qdrant.close()
            sqlite.close()

        return result
