"""
多智能体 MVP：顺序两阶段（analyst 全链路 → synthesizer 整合），经 trace / WS 暴露 agent_* 事件。
"""

from __future__ import annotations

from collections.abc import Callable

from backend.kernel.blackboard import Blackboard
from backend.kernel.run_context import RunContext
from backend.kernel.trace import TraceWriter
from backend.rag.citation import Citation
from backend.rag.evidence_builder import EvidenceEntry
from backend.runners.chat_runner import ChatRunner, ChatRunResult


def _dedupe_citations(cites: list[Citation]) -> list[Citation]:
    seen: set[str] = set()
    out: list[Citation] = []
    for c in cites:
        if c.chunk_id in seen:
            continue
        seen.add(c.chunk_id)
        out.append(c)
    return out


def _dedupe_evidence(entries: list[EvidenceEntry]) -> list[EvidenceEntry]:
    seen: set[str] = set()
    out: list[EvidenceEntry] = []
    for e in entries:
        if e.chunk_id in seen:
            continue
        seen.add(e.chunk_id)
        out.append(e)
    return out


def run_sequential_two_agent(
    *,
    runner: ChatRunner,
    ctx: RunContext,
    trace: TraceWriter,
    blackboard: Blackboard,
    effective_query: str,
    version_scope: list[str] | None,
    stream: bool,
    stream_writer: Callable[[str, str], None] | None,
    prompt_addons: list[str] | None,
    worker_template_blocks: list[str] | None = None,
    synthesizer_template_blocks: list[str] | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    rolling_summary: str | None = None,
    reconstructed_memory: str | None = None,
) -> ChatRunResult:
    """
    Sub-agent 1（analyst）：与用户问题相同，走完整 retrieve → generate（流式可关闭）。
    Sub-agent 2（synthesizer）：在 analyst 草稿上整合为最终答复（默认开启流式）。
    """
    base_addons = list(prompt_addons or [])
    worker_blocks = list(worker_template_blocks or [])
    synth_tpl = list(synthesizer_template_blocks or [])
    phase1_addons = [*base_addons, *worker_blocks]

    def _muted(_kind: str, _text: str) -> None:
        return

    # ─── Phase 1: analyst ─────────────────────────────────────────
    trace.emit(
        "agent_spawned",
        {
            "agent_id": "sub_analyst",
            "profile_id": "analyst",
            "task_summary": "检索与基于证据的初答",
        },
    )
    trace.emit(
        "agent_progress",
        {
            "agent_id": "sub_analyst",
            "step": 1,
            "detail": "retrieve_and_generate",
        },
    )
    try:
        r1 = runner.run(
            ctx,
            effective_query,
            trace,
            blackboard,
            version_scope=version_scope,
            stream=stream,
            stream_writer=_muted if stream else None,
            prompt_addons=phase1_addons,
            conversation_history=conversation_history,
            rolling_summary=rolling_summary,
            reconstructed_memory=reconstructed_memory,
        )
    except Exception as e:  # noqa: BLE001
        trace.emit(
            "agent_failed",
            {"agent_id": "sub_analyst", "message": str(e)},
        )
        raise

    trace.emit(
        "agent_completed",
        {
            "agent_id": "sub_analyst",
            "output_summary": (r1.answer or "")[:800],
        },
    )

    # ─── Phase 2: synthesizer ─────────────────────────────────────
    draft = (r1.answer or "").strip()
    if len(draft) > 12_000:
        draft = draft[:12_000] + "\n…(truncated for synthesizer)"

    synth_addon = (
        "你是 synthesizer。请基于下述 analyst 草稿整合最终答复，保持事实一致，避免臆造。\n\n"
        f"【用户原始问题】\n{effective_query}\n\n"
        f"【分析智能体草稿】\n{draft}\n\n"
        "要求：\n"
        "1) 输出对用户友好、结构清晰的最终答案；\n"
        "2) 若草稿已有引用编号，尽量保留其语义对应；\n"
        "3) 不要把本段系统说明原样复述给用户。"
    )
    phase2_addons = [*base_addons, *synth_tpl, synth_addon]

    trace.emit(
        "agent_spawned",
        {
            "agent_id": "sub_synthesizer",
            "profile_id": "synthesizer",
            "task_summary": "整合 analyst 输出并生成终稿",
        },
    )
    trace.emit(
        "agent_progress",
        {
            "agent_id": "sub_synthesizer",
            "step": 1,
            "detail": "merge_and_polish",
        },
    )
    try:
        r2 = runner.run(
            ctx,
            effective_query,
            trace,
            blackboard,
            version_scope=version_scope,
            stream=stream,
            stream_writer=stream_writer if stream else None,
            prompt_addons=phase2_addons,
            conversation_history=conversation_history,
            rolling_summary=rolling_summary,
            reconstructed_memory=reconstructed_memory,
        )
    except Exception as e:  # noqa: BLE001
        trace.emit(
            "agent_failed",
            {"agent_id": "sub_synthesizer", "message": str(e)},
        )
        trace.emit(
            "merge_started",
            {"strategy": "fallback_analyst_only", "error": str(e)},
        )
        return ChatRunResult(
            answer=r1.answer,
            citations=r1.citations,
            evidence_entries=r1.evidence_entries,
            degraded=True,
            run_id=ctx.run_id,
            retrieval_state={
                "multi_agent": True,
                "analyst": r1.retrieval_state,
                "synthesizer_error": str(e),
            },
            degrade_reason=f"synthesizer_failed:{e}",
            thinking=r1.thinking,
        )

    trace.emit(
        "agent_completed",
        {
            "agent_id": "sub_synthesizer",
            "output_summary": (r2.answer or "")[:800],
        },
    )

    trace.emit(
        "merge_started",
        {
            "strategy": "sequential_two_phase",
            "sub_agents": ["sub_analyst", "sub_synthesizer"],
        },
    )

    citations = _dedupe_citations(r1.citations + r2.citations)
    evidence_entries = _dedupe_evidence(r1.evidence_entries + r2.evidence_entries)
    degraded = bool(r1.degraded or r2.degraded)
    dr = r2.degrade_reason or r1.degrade_reason

    return ChatRunResult(
        answer=r2.answer,
        citations=citations,
        evidence_entries=evidence_entries,
        degraded=degraded,
        run_id=ctx.run_id,
        retrieval_state={
            "multi_agent": True,
            "analyst": r1.retrieval_state,
            "synthesizer": r2.retrieval_state,
        },
        degrade_reason=dr,
        thinking=r2.thinking,
    )
