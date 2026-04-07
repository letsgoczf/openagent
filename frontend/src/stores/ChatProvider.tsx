"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  CitationDTO,
  EvidenceEntryDTO,
  SubAgentRun,
  SubAgentStatus,
} from "@/types/chat";
import { wsUrl } from "@/lib/api";
import { readWsPayload, subAgentTaskSummary } from "@/lib/wsPayload";

export type ChatStatus = "idle" | "connecting" | "streaming" | "done" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string;
  citations?: CitationDTO[];
  evidenceEntries?: EvidenceEntryDTO[];
}

export interface TraceLine {
  type: string;
  detail: string;
}

interface ChatContextValue {
  messages: ChatMessage[];
  sendQuery: (query: string) => void;
  status: ChatStatus;
  error: string | null;
  thinkingBuffer: string;
  assistantBuffer: string;
  traceLines: TraceLine[];
  /** multi 模式下 Orchestrator 派生的子智能体（``chat.agent_*``） */
  subAgents: SubAgentRun[];
  clearMessages: () => void;
  /** 当前轮次（最近一次 completed）的证据与引用，供侧栏与 citation 跳转 */
  lastEvidenceEntries: EvidenceEntryDTO[];
  lastCitations: CitationDTO[];
  activeChunkId: string | null;
  setActiveChunkId: (id: string | null) => void;
}

const ChatContext = createContext<ChatContextValue | null>(null);

const EXTRA_TRACE_TYPES = new Set([
  "chat.run_started",
  "chat.mode_selected",
  "chat.plan_generated",
  "chat.plan_step_started",
  "chat.plan_step_completed",
  "chat.reflect_update",
  "chat.clarify_requested",
  "chat.ocr_pages_selected",
  "chat.merge_started",
  "chat.conflict_detected",
]);

function upsertSubAgent(
  prev: SubAgentRun[],
  patch: Partial<SubAgentRun> & { agent_id: string }
): SubAgentRun[] {
  const i = prev.findIndex((s) => s.agent_id === patch.agent_id);
  if (i < 0) {
    const next: SubAgentRun = {
      agent_id: patch.agent_id,
      status: (patch.status as SubAgentStatus) ?? "running",
      profile_id: patch.profile_id,
      task_summary: patch.task_summary,
      lastProgress: patch.lastProgress,
      outputSummary: patch.outputSummary,
      errorMessage: patch.errorMessage,
    };
    return [...prev, next];
  }
  const cur = prev[i]!;
  const merged: SubAgentRun = { ...cur, ...patch };
  if (patch.lastProgress !== undefined) {
    merged.lastProgress = patch.lastProgress;
  }
  return prev.map((s, j) => (j === i ? merged : s));
}

function parseList<T>(raw: unknown): T[] {
  if (!Array.isArray(raw)) return [];
  return raw as T[];
}

function normalizeAnswerText(raw: unknown): string {
  if (raw == null) return "";
  if (typeof raw === "string") return raw;
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  if (typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    const cand = obj.content ?? obj.text ?? obj.answer;
    if (typeof cand === "string") return cand;
    try {
      return JSON.stringify(raw, null, 2);
    } catch {
      return String(raw);
    }
  }
  return String(raw);
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [thinkingBuffer, setThinkingBuffer] = useState("");
  const [assistantBuffer, setAssistantBuffer] = useState("");
  const [traceLines, setTraceLines] = useState<TraceLine[]>([]);
  const [lastEvidenceEntries, setLastEvidenceEntries] = useState<
    EvidenceEntryDTO[]
  >([]);
  const [lastCitations, setLastCitations] = useState<CitationDTO[]>([]);
  const [activeChunkId, setActiveChunkId] = useState<string | null>(null);
  const [subAgents, setSubAgents] = useState<SubAgentRun[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const thinkingRef = useRef("");
  const assistantRef = useRef("");

  const appendTrace = useCallback((type: string, detail: string) => {
    setTraceLines((prev) => [...prev.slice(-200), { type, detail }]);
  }, []);

  const sendQuery = useCallback(
    (query: string) => {
      const q = query.trim();
      if (!q) return;

      thinkingRef.current = "";
      assistantRef.current = "";
      setError(null);
      setThinkingBuffer("");
      setAssistantBuffer("");
      setTraceLines([]);
      setSubAgents([]);
      setLastEvidenceEntries([]);
      setLastCitations([]);
      setActiveChunkId(null);
      setStatus("connecting");

      const userId = `u_${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        { id: userId, role: "user", content: q },
      ]);

      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("streaming");
        ws.send(
          JSON.stringify({
            type: "chat.start",
            client_request_id: `req_${Date.now()}`,
            query: q,
            stream: true,
          })
        );
      };

      ws.onmessage = (ev) => {
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(String(ev.data)) as Record<string, unknown>;
        } catch {
          appendTrace("parse_error", String(ev.data).slice(0, 200));
          return;
        }

        const t = String(data.type ?? "");

        if (t === "chat.delta") {
          const kind = String(data.delta_kind ?? "content");
          const delta = String(data.delta ?? "");
          if (kind === "thinking") {
            thinkingRef.current += delta;
            setThinkingBuffer(thinkingRef.current);
          } else if (kind === "content" || kind === "citations") {
            assistantRef.current += delta;
            setAssistantBuffer(assistantRef.current);
          }
          return;
        }

        if (
          t === "chat.retrieval_update" ||
          t === "chat.evidence_update" ||
          t === "chat.tool_call_started" ||
          t === "chat.tool_call_finished" ||
          t === "chat.tool_call_failed"
        ) {
          appendTrace(t, JSON.stringify(data.payload ?? {}));
          return;
        }

        if (EXTRA_TRACE_TYPES.has(t)) {
          appendTrace(t, JSON.stringify(data.payload ?? {}));
          return;
        }

        if (t === "chat.agent_spawned") {
          const p = readWsPayload(data);
          const agent_id = String(p.agent_id ?? "").trim();
          const detail = JSON.stringify(p);
          if (!agent_id) {
            appendTrace(t, detail);
            return;
          }
          setSubAgents((prev) =>
            upsertSubAgent(prev, {
              agent_id,
              profile_id:
                p.profile_id != null ? String(p.profile_id) : undefined,
              task_summary: subAgentTaskSummary(p),
              status: "running",
            })
          );
          appendTrace(t, detail);
          return;
        }

        if (t === "chat.agent_progress") {
          const p = readWsPayload(data);
          const agent_id = String(p.agent_id ?? "").trim();
          if (!agent_id) {
            appendTrace(t, JSON.stringify(p));
            return;
          }
          const step = p.step != null ? String(p.step) : "";
          const detailStr =
            p.detail != null
              ? String(p.detail)
              : p.message != null
                ? String(p.message)
                : "";
          const progress =
            [step && `step ${step}`, detailStr].filter(Boolean).join(" · ") ||
            JSON.stringify(p);
          setSubAgents((prev) =>
            upsertSubAgent(prev, { agent_id, lastProgress: progress })
          );
          appendTrace(t, JSON.stringify(p));
          return;
        }

        if (t === "chat.agent_completed") {
          const p = readWsPayload(data);
          const agent_id = String(p.agent_id ?? "").trim();
          if (!agent_id) {
            appendTrace(t, JSON.stringify(p));
            return;
          }
          const outputSummary =
            p.output_summary != null
              ? String(p.output_summary)
              : p.summary != null
                ? String(p.summary)
                : undefined;
          setSubAgents((prev) =>
            upsertSubAgent(prev, {
              agent_id,
              status: "completed",
              outputSummary: outputSummary || undefined,
            })
          );
          appendTrace(t, JSON.stringify(p));
          return;
        }

        if (t === "chat.agent_failed") {
          const p = readWsPayload(data);
          const agent_id = String(p.agent_id ?? "").trim();
          const err =
            p.message != null
              ? String(p.message)
              : p.error != null
                ? String(p.error)
                : JSON.stringify(p);
          if (!agent_id) {
            appendTrace(t, err);
            return;
          }
          setSubAgents((prev) =>
            upsertSubAgent(prev, {
              agent_id,
              status: "failed",
              errorMessage: err,
            })
          );
          appendTrace(t, JSON.stringify(p));
          return;
        }

        if (t === "chat.completed") {
          const answer = normalizeAnswerText(data.answer);
          const finalText = assistantRef.current || answer;
          const think = thinkingRef.current;
          const citations = parseList<CitationDTO>(data.citations);
          const evidenceEntries = parseList<EvidenceEntryDTO>(
            data.evidence_entries
          );

          setLastCitations(citations);
          setLastEvidenceEntries(evidenceEntries);

          setMessages((prev) => [
            ...prev,
            {
              id: `a_${Date.now()}`,
              role: "assistant",
              content: finalText,
              thinking: think || undefined,
              citations: citations.length ? citations : undefined,
              evidenceEntries: evidenceEntries.length
                ? evidenceEntries
                : undefined,
            },
          ]);
          assistantRef.current = "";
          thinkingRef.current = "";
          setAssistantBuffer("");
          setThinkingBuffer("");
          setStatus("done");
          ws.close();
          return;
        }

        if (t === "chat.failed") {
          const msg =
            (data.error as { message?: string } | undefined)?.message ??
            "unknown error";
          setError(msg);
          setStatus("error");
          ws.close();
        }
      };

      ws.onerror = () => {
        setError("WebSocket error");
        setStatus("error");
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    },
    [appendTrace]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setTraceLines([]);
    setSubAgents([]);
    setError(null);
    setStatus("idle");
    setLastEvidenceEntries([]);
    setLastCitations([]);
    setActiveChunkId(null);
  }, []);

  const value = useMemo(
    () => ({
      messages,
      sendQuery,
      status,
      error,
      thinkingBuffer,
      assistantBuffer,
      traceLines,
      subAgents,
      clearMessages,
      lastEvidenceEntries,
      lastCitations,
      activeChunkId,
      setActiveChunkId,
    }),
    [
      messages,
      sendQuery,
      status,
      error,
      thinkingBuffer,
      assistantBuffer,
      traceLines,
      subAgents,
      clearMessages,
      lastEvidenceEntries,
      lastCitations,
      activeChunkId,
    ]
  );

  return (
    <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
  );
}

export function useChat(): ChatContextValue {
  const ctx = useContext(ChatContext);
  if (!ctx) {
    throw new Error("useChat must be used within ChatProvider");
  }
  return ctx;
}
