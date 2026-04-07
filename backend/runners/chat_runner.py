from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.config_loader import (
    OpenAgentSettings,
    load_config,
    resolve_repo_relative_path,
)
from backend.kernel.blackboard import Blackboard
from backend.kernel.budget import Budget
from backend.kernel.run_context import RunContext
from backend.kernel.trace import TraceWriter
from backend.models.embeddings import embed_text
from backend.models.factory import create_llm_adapter, create_tokenizer_service
from backend.models.base import ChatResponse, LLMAdapter, StreamPart
from backend.models.tokenizer import TokenizerService
from backend.rag.citation import Citation
from backend.rag.evidence_builder import EvidenceEntry
from backend.rag.service import RetrievalResult, RetrievalService
from backend.registry.tool_gateway import ToolGateway
from backend.registry.tool_registry import ToolRegistry
from backend.registry.service import RegistryService
from backend.runners.composer import (
    build_evidence_block,
    build_messages,
    format_citations_footer,
    load_constitution_from_file,
    trim_evidence_entries_to_budget,
)
from backend.runners.tool_loop import ToolGatewayStub, chat_until_no_tools, run_tool_loop_round
from backend.storage.factory import build_qdrant_client
from backend.storage.qdrant_store import QdrantStore
from backend.storage.sqlite_store import SQLiteStore


@dataclass
class ChatRunResult:
    answer: str
    citations: list[Citation]
    evidence_entries: list[EvidenceEntry]
    degraded: bool
    run_id: str
    retrieval_state: dict[str, Any]
    degrade_reason: str | None = None


class ChatRunner:
    """single profile：retrieve → compose → generate → (tool loop) → citations 脚注。"""

    def __init__(
        self,
        settings: OpenAgentSettings,
        sqlite: SQLiteStore,
        qdrant: QdrantStore,
        llm: LLMAdapter,
        tokenizer: TokenizerService,
        *,
        constitution_path: Path | None = None,
        registry: RegistryService | None = None,
        tool_schemas: list[dict[str, Any]] | None = None,
    ) -> None:
        self._settings = settings
        self._sqlite = sqlite
        self._qdrant = qdrant
        self._llm = llm
        self._tokenizer = tokenizer
        self._constitution_path = constitution_path
        self._retrieval = RetrievalService(sqlite, qdrant, tokenizer, settings=settings)
        self._registry = registry
        self._tool_schemas = tool_schemas or []

        # 构建 tool gateway
        if registry is not None:
            self._tool_gateway: ToolGateway | ToolGatewayStub = registry.tool_gateway
        else:
            self._tool_gateway = ToolGatewayStub()

    def run(
        self,
        ctx: RunContext,
        query: str,
        trace: TraceWriter,
        blackboard: Blackboard,
        *,
        version_scope: list[str] | None = None,
        stream: bool = False,
        stream_writer: Callable[[str, str], None] | None = None,
        prompt_addons: list[str] | None = None,
    ) -> ChatRunResult:
        blackboard.append("run", "retrieving", {"query_len": len(query)})
        trace.emit("retrieval_update", {"phase": "start", "query_preview": query[:120]})

        if ctx.budget.wall_clock_exceeded():
            ctx.mark_degraded("wall_clock")
            trace.emit("completed", {"degraded": True, "reason": "wall_clock"})
            return ChatRunResult(
                answer="",
                citations=[],
                evidence_entries=[],
                degraded=True,
                run_id=ctx.run_id,
                retrieval_state={},
                degrade_reason="wall_clock",
            )

        try:
            qvec = embed_text(query, settings=self._settings)
        except Exception as e:  # noqa: BLE001
            ctx.mark_degraded(f"embedding_failed:{e}")
            trace.emit("retrieval_update", {"error": str(e)})
            qvec = []

        rr: RetrievalResult | None = None
        # P6: 受 Registry 控制，仅允许访问已注册的 collection
        allowed_ids = self._registry.rag_registry.get_allowed_ids() if self._registry else None
        if qvec:
            rr = self._retrieval.retrieve(
                query,
                qvec,
                version_scope=version_scope,
                persist_evidence_cache=True,
                candidate_debug=False,
                allowed_collection_ids=allowed_ids,
            )
        else:
            rr = RetrievalResult(
                evidence_entries=[],
                citations=[],
                retrieval_state={"dense_hits": 0, "keyword_hits": 0},
                candidate_debug=None,
            )

        trace.emit(
            "retrieval_update",
            {"phase": "done", **rr.retrieval_state},
        )
        trace.emit(
            "evidence_update",
            {
                "count": len(rr.evidence_entries),
                "chunk_ids": [e.chunk_id for e in rr.evidence_entries],
            },
        )
        blackboard.append(
            "evidence",
            "evidence_ready",
            {"count": len(rr.evidence_entries)},
        )

        const_text = load_constitution_from_file(self._constitution_path)
        # 总 evidence 预算截断：避免多条合计超出模型上下文窗口
        max_ev = self._settings.evidence.max_assembled_evidence_tokens
        trimmed_entries = trim_evidence_entries_to_budget(
            rr.evidence_entries, self._tokenizer, max_assembled_tokens=max_ev
        )
        if len(trimmed_entries) != len(rr.evidence_entries):
            trace.emit(
                "evidence_update",
                {
                    "trimmed": True,
                    "before": len(rr.evidence_entries),
                    "after": len(trimmed_entries),
                    "max_assembled_evidence_tokens": max_ev,
                },
            )
        ev_block = build_evidence_block(trimmed_entries)
        messages = build_messages(
            constitution=const_text,
            query=query,
            evidence_block=ev_block,
            prompt_addons=prompt_addons,
        )

        if not ctx.budget.can_call_llm() or ctx.budget.token_budget_exceeded():
            ctx.mark_degraded("llm_or_token_budget")
            footer = format_citations_footer(rr.citations)
            trace.emit(
                "completed",
                {
                    "degraded": True,
                    "reason": "budget",
                    "citations": len(rr.citations),
                },
            )
            msg = "[Degraded: LLM budget exhausted]\n"
            return ChatRunResult(
                answer=msg + footer,
                citations=rr.citations,
                evidence_entries=rr.evidence_entries,
                degraded=True,
                run_id=ctx.run_id,
                retrieval_state=rr.retrieval_state,
                degrade_reason="llm_or_token_budget",
            )

        # 带 tool 注册时发送 LLM tool schemas + 执行 tool loop
        tools = self._tool_schemas if self._tool_schemas else None
        body = ""
        tool_calls: list[dict[str, Any]] | None = None

        try:
            raw = self._llm.chat(messages, stream=stream, tools=tools)
            if isinstance(raw, str):
                # 旧式：纯字符串（兼容老 adapter）
                body = raw
            elif isinstance(raw, ChatResponse):
                # 新式：携带 tool_calls + thinking
                body = raw.content
                tool_calls = raw.tool_calls or None
                if raw.thinking and stream_writer:
                    for line in raw.thinking.splitlines():
                        stream_writer("thinking", line + "\n")
            else:
                # 流式：迭代 StreamPart
                tool_calls = None
                parts: list[str] = []
                think_parts: list[str] = []
                for item in raw:
                    if isinstance(item, tuple):
                        kind, chunk = item[0], item[1]
                        if kind == "content":
                            parts.append(chunk)
                        elif kind == "thinking":
                            think_parts.append(chunk)
                        elif kind == "tool_calls":
                            # 流尾携带 tool_calls 数据
                            import json
                            try:
                                tool_calls = json.loads(chunk) if isinstance(chunk, str) else chunk
                            except (json.JSONDecodeError, TypeError):
                                tool_calls = None
                        if stream_writer:
                            stream_writer(kind, chunk)
                    else:
                        parts.append(str(item))
                        if stream_writer:
                            stream_writer("content", str(item))
                body_only = "".join(parts)
                if think_parts:
                    body = (
                        "--- Thinking ---\n"
                        + "".join(think_parts)
                        + "\n--- /Thinking ---\n\n"
                        + body_only.strip()
                    )
                else:
                    body = body_only
        except Exception as e:  # noqa: BLE001
            ctx.mark_degraded(f"llm_error:{e}")
            trace.emit("completed", {"degraded": True, "error": str(e)})
            footer = format_citations_footer(rr.citations)
            return ChatRunResult(
                answer=f"[LLM error: {e}]\n" + footer,
                citations=rr.citations,
                evidence_entries=rr.evidence_entries,
                degraded=True,
                run_id=ctx.run_id,
                retrieval_state=rr.retrieval_state,
                degrade_reason=str(e),
            )

        ctx.budget.record_llm_call()

        # tool loop 调用（仅当有真实 gateway 且有 tool_calls 时）
        if tool_calls and not isinstance(self._tool_gateway, ToolGatewayStub):
            tc_results = run_tool_loop_round(
                budget=ctx.budget,
                blackboard=blackboard,
                gateway=self._tool_gateway,
                tool_calls=tool_calls,
            )
            # P6: 将每个 tool_call 的开始/结束写入 trace（用于验收与回放）。
            for idx, (tc, r) in enumerate(zip(tool_calls, tc_results)):
                tc_id = tc.get("id") or r.get("tool_call_id") or f"tc_{idx}"
                tool_name = (tc.get("function") or {}).get("name") or r.get("tool") or ""
                code = r.get("code") or ""
                payload_preview = str(r.get("payload") or "")[:500]

                trace.emit(
                    "tool_call_started",
                    {
                        "tool_call_id": tc_id,
                        "tool": tool_name,
                        "code": code,
                        "payload_preview": payload_preview,
                    },
                )
                if r.get("result") is True:
                    trace.emit(
                        "tool_call_finished",
                        {
                            "tool_call_id": tc_id,
                            "tool": tool_name,
                            "code": code,
                            "payload_preview": payload_preview,
                        },
                    )
                else:
                    trace.emit(
                        "tool_call_failed",
                        {
                            "tool_call_id": tc_id,
                            "tool": tool_name,
                            "code": code,
                            "payload_preview": payload_preview,
                        },
                    )

            trace.emit("tool_loop_done", {"tool_calls": len(tool_calls)})

        footer = format_citations_footer(rr.citations)
        body_stripped = body.strip()
        full_answer = body_stripped + footer
        if stream and stream_writer and footer:
            stream_writer("citations", footer)

        trace.emit(
            "completed",
            {
                "answer_chars": len(body_stripped),
                "citations": len(rr.citations),
                "degraded": ctx.degraded,
                "streamed": stream,
            },
        )
        blackboard.append("run", "completed", {"citations": len(rr.citations)})

        return ChatRunResult(
            answer=full_answer,
            citations=rr.citations,
            evidence_entries=rr.evidence_entries,
            degraded=ctx.degraded,
            run_id=ctx.run_id,
            retrieval_state=rr.retrieval_state,
            degrade_reason=ctx.degrade_reason,
        )


def build_chat_runner(
    settings: OpenAgentSettings | None = None,
    *,
    constitution_path: Path | None = None,
    registry: RegistryService | None = None,
    tool_schemas: list[dict[str, Any]] | None = None,
) -> tuple[ChatRunner, SQLiteStore, QdrantStore]:
    """构造默认存储、Qdrant 与 Runner（调用方负责在适当时机关闭 store / qdrant client）。"""
    cfg = settings or load_config()
    eff_constitution: Path | None = constitution_path
    if eff_constitution is None and cfg.constitution_path:
        eff_constitution = resolve_repo_relative_path(cfg.constitution_path)
    sqlite = SQLiteStore(cfg.storage.sqlite_path)
    dim = cfg.models.embedding.vector_dimensions
    if dim is None:
        try:
            dim = len(embed_text("ping", settings=cfg))
        except Exception as e:
            msg = (
                "无法自动探测 embedding 维度（多为 Ollama embed 不可用：未启动、502、或未 pull 模型）。"
                "请在 openagent.yaml 中设置 models.embedding.vector_dimensions（"
                "nomic-embed-text 一般为 768）；并执行 ollama serve、ollama pull <embedding_model>。"
            )
            raise RuntimeError(msg) from e
    qclient = build_qdrant_client(cfg.storage.qdrant)
    qdrant = QdrantStore(
        cfg.storage.qdrant.collection_name,
        vector_size=dim,
        client=qclient,
    )
    llm = create_llm_adapter(cfg)
    tok = create_tokenizer_service(cfg)
    runner = ChatRunner(
        cfg,
        sqlite,
        qdrant,
        llm,
        tok,
        constitution_path=eff_constitution,
        registry=registry,
        tool_schemas=tool_schemas,
    )
    return runner, sqlite, qdrant
