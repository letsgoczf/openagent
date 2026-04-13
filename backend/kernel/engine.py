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
from backend.memory.consolidation import run_consolidation_if_needed
from backend.memory.reconstruct import (
    embedding_vector_size,
    persist_turn_fragments,
    retrieve_reconstructed_fragment_context,
)
from backend.memory.session_store import (
    fetch_history_messages,
    persist_user_assistant_turns,
)
from backend.prompts.catalog import discover_agent_templates, load_template_bodies
from backend.prompts.mentions import extract_forced_agent_templates
from backend.prompts.planner import plan_prompt_templates
from backend.models.factory import create_tokenizer_service
from backend.registry.skill_registry import SkillRegistry
from backend.registry.skill_router import resolve_matched_skills
from backend.registry.service import RegistryService
from backend.runners.chat_runner import ChatRunResult, build_chat_runner
from backend.runners.composer import strip_citations_footer_from_answer
from backend.storage.qdrant_store import QdrantStore


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

        catalog = discover_agent_templates(settings=self.settings)
        allowed_ids = frozenset(e.id for e in catalog)
        forced_template_ids, effective_query = extract_forced_agent_templates(
            effective_query,
            allowed_ids=allowed_ids,
        )
        if forced_template_ids:
            decision = {**decision, "effective_query": effective_query}

        # 构建 Registry；技能匹配与 tool 白名单在拿到 LLM 后执行（可选 LLM skill 路由）
        registry = RegistryService.from_config(self.settings)
        tool_schemas = registry.get_tool_schemas()

        runner, sqlite, qdrant = build_chat_runner(
            self.settings,
            constitution_path=self.constitution_path,
            registry=registry,
            tool_schemas=tool_schemas,
        )
        trace = TraceWriter(sqlite, run_id, on_emit=trace_sink)
        bb = Blackboard()
        tok = create_tokenizer_service(self.settings)

        mem_qdrant: QdrantStore | None = None
        if self.settings.memory.enabled and self.settings.memory.fragments_enabled:
            mem_qdrant = QdrantStore(
                self.settings.storage.qdrant.memory_collection_name,
                vector_size=embedding_vector_size(self.settings),
                client=qdrant.client,
            )

        conversation_history: list[dict[str, str]] | None = None
        rolling_summary: str | None = None
        reconstructed_memory: str | None = None

        trace.emit("run_started", {"session_id": sid, "run_id": run_id})
        trace.emit("mode_selected", decision)
        bb.append("kernel", "mode_selected", decision)

        matched_skills = resolve_matched_skills(
            registry.skill_registry,
            effective_query,
            llm=runner.llm_adapter,
            budget=bud,
            trace=trace,
            settings=self.settings,
        )
        registry.tool_registry.set_allowlist(
            SkillRegistry.merged_allowlist_from_matches(matched_skills)
        )
        prompt_addons = SkillRegistry.prompt_addons_from_matches(matched_skills)

        if self.settings.memory.enabled:
            conversation_history, rolling_summary = fetch_history_messages(
                sqlite, self.settings.memory, sid, tok
            )
            if mem_qdrant is not None:
                rc = retrieve_reconstructed_fragment_context(
                    sqlite,
                    mem_qdrant,
                    self.settings,
                    sid,
                    effective_query,
                    tok,
                    budget=bud,
                    llm=runner.llm_adapter,
                    trace=trace,
                )
                reconstructed_memory = rc.strip() or None
            trace.emit(
                "memory_read",
                {
                    "session_id": sid,
                    "history_messages": len(conversation_history),
                    "rolling_summary_chars": len(rolling_summary or ""),
                    "reconstructed_fragment_chars": len(reconstructed_memory or ""),
                },
            )

        # 写 registry 相关信息到 trace
        if matched_skills:
            trace.emit(
                "skills_matched",
                {"skills": [s.skill_id for s in matched_skills]},
            )
        if prompt_addons:
            bb.append("kernel", "skill_addons", {"addons": prompt_addons})

        skill_addons = list(prompt_addons or [])
        worker_blocks: list[str] = []
        synth_blocks: list[str] = []
        pm = self.settings.prompt_management
        cap = pm.max_templates_per_role
        forced_worker: list[str] = (
            forced_template_ids[:cap] if len(forced_template_ids) > cap else list(forced_template_ids)
        )
        if len(forced_template_ids) > cap and trace:
            trace.emit(
                "agent_mention_forced",
                {
                    "truncated": True,
                    "requested": forced_template_ids,
                    "applied": forced_worker,
                    "max_templates_per_role": cap,
                },
            )

        if forced_worker:
            worker_blocks = load_template_bodies(
                forced_worker,
                entries=catalog,
                max_chars_per_template=pm.max_chars_per_template,
            )
            if trace:
                trace.emit(
                    "prompt_plan",
                    {
                        "forced_via_mention": True,
                        "worker_templates": forced_worker,
                        "synthesizer_templates": [],
                        "skipped_planner": True,
                    },
                )
        elif self.settings.prompt_management.enabled and catalog:
            plan = plan_prompt_templates(
                query=effective_query,
                mode=str(decision.get("mode") or "single"),
                llm=runner.llm_adapter,
                budget=bud,
                trace=trace,
                settings=self.settings,
                catalog=catalog,
            )
            worker_blocks = load_template_bodies(
                plan.worker_templates,
                entries=catalog,
                max_chars_per_template=pm.max_chars_per_template,
            )
            if decision.get("mode") == "multi":
                synth_blocks = load_template_bodies(
                    plan.synthesizer_templates,
                    entries=catalog,
                    max_chars_per_template=pm.max_chars_per_template,
                )

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
                    prompt_addons=skill_addons,
                    worker_template_blocks=worker_blocks,
                    synthesizer_template_blocks=synth_blocks,
                    conversation_history=conversation_history,
                    rolling_summary=rolling_summary,
                    reconstructed_memory=reconstructed_memory,
                )
            else:
                combined_addons = [*skill_addons, *worker_blocks]
                result = runner.run(
                    ctx,
                    effective_query,
                    trace,
                    bb,
                    version_scope=version_scope,
                    stream=stream,
                    stream_writer=stream_writer,
                    prompt_addons=combined_addons,
                    conversation_history=conversation_history,
                    rolling_summary=rolling_summary,
                    reconstructed_memory=reconstructed_memory,
                )
            if self.settings.memory.enabled:
                body = strip_citations_footer_from_answer(result.answer)
                trace.emit(
                    "memory_write",
                    {
                        "session_id": sid,
                        "user_chars": len(effective_query),
                        "assistant_chars": len(body),
                    },
                )
                persist_user_assistant_turns(
                    sqlite,
                    self.settings.memory,
                    sid,
                    result.run_id,
                    effective_query,
                    body,
                    tok,
                )
                if self.settings.memory.consolidation_enabled:
                    run_consolidation_if_needed(
                        store=sqlite,
                        cfg=self.settings.memory,
                        session_id=sid,
                        budget=bud,
                        llm=runner.llm_adapter,
                        tokenizer=tok,
                        trace=trace,
                    )
                if mem_qdrant is not None:
                    persist_turn_fragments(
                        sqlite,
                        mem_qdrant,
                        self.settings,
                        sid,
                        result.run_id,
                        effective_query,
                        body,
                        trace,
                        budget=bud,
                        llm=runner.llm_adapter,
                    )
        finally:
            qdrant.close()
            sqlite.close()

        return result
