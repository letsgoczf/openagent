"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  ChatMessage,
  CitationDTO,
  EvidenceEntryDTO,
  SubAgentRun,
  SubAgentStatus,
} from "@/types/chat";
import {
  CHAT_SESSIONS_VERSION,
  clearLegacyChatSessionsStorage,
  createEmptySession,
  loadChatSessionsFile,
  type ChatSessionPersisted,
} from "@/lib/chatSessionPersistence";
import {
  fetchChatSessionsState,
  putChatSessionsState,
} from "@/lib/chatSessionsApi";
import { wsUrl } from "@/lib/api";
import {
  stripEmbeddedThinkingBlock,
  stripLegacyCitationsAppendix,
} from "@/lib/stripLegacyCitationsAppendix";
import { readWsPayload, subAgentTaskSummary } from "@/lib/wsPayload";

export type ChatStatus = "idle" | "connecting" | "streaming" | "done" | "error";

export interface TraceLine {
  type: string;
  detail: string;
}

function titleFromFirstQuery(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  if (!t) return "新会话";
  const max = 40;
  return t.length <= max ? t : `${t.slice(0, max)}…`;
}

interface ChatContextValue {
  sessionsReady: boolean;
  sessions: ChatSessionPersisted[];
  activeSessionId: string | null;
  createSession: () => void;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => void;
  messages: ChatMessage[];
  sendQuery: (query: string) => void;
  /** 发送 ``chat.stop`` 停止当前生成（流式时在服务端协作中断） */
  stopGeneration: () => void;
  status: ChatStatus;
  error: string | null;
  thinkingBuffer: string;
  assistantBuffer: string;
  traceLines: TraceLine[];
  /** multi 模式下 Orchestrator 派生的子智能体（``chat.agent_*``） */
  subAgents: SubAgentRun[];
  clearMessages: () => void;
  /** 当前会话最近一次 completed 的证据与引用，供侧栏与 citation 跳转 */
  lastEvidenceEntries: EvidenceEntryDTO[];
  lastCitations: CitationDTO[];
  /** 本轮流式生成中已由 citation_context 下发的引用（与正文 [n] 对齐） */
  streamingCitations: CitationDTO[];
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
  if (typeof raw === "string") return stripLegacyCitationsAppendix(raw);
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  if (typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    const cand = obj.content ?? obj.text ?? obj.answer;
    if (typeof cand === "string") return stripLegacyCitationsAppendix(cand);
    try {
      return JSON.stringify(raw, null, 2);
    } catch {
      return String(raw);
    }
  }
  return String(raw);
}

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<ChatSessionPersisted[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionsReady, setSessionsReady] = useState(false);

  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [thinkingBuffer, setThinkingBuffer] = useState("");
  const [assistantBuffer, setAssistantBuffer] = useState("");
  const [streamingCitations, setStreamingCitations] = useState<CitationDTO[]>(
    []
  );
  const [traceLines, setTraceLines] = useState<TraceLine[]>([]);
  const [activeChunkId, setActiveChunkId] = useState<string | null>(null);
  const [subAgents, setSubAgents] = useState<SubAgentRun[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const thinkingRef = useRef("");
  const assistantRef = useRef("");
  const activeSessionIdRef = useRef<string | null>(null);
  const streamingSessionIdRef = useRef<string | null>(null);
  /** 与当前 WebSocket 轮次对齐，丢弃旧连接晚到的 chat.* 事件，避免污染新会话侧栏 */
  const activeRequestIdRef = useRef<string | null>(null);
  const persistSkipRef = useRef(true);
  const persistTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const remote = await fetchChatSessionsState();
        if (cancelled) return;
        if (remote.sessions.length > 0) {
          const activeOk = remote.sessions.some(
            (s) => s.id === remote.activeSessionId
          );
          setSessions(remote.sessions);
          setActiveSessionId(
            activeOk ? remote.activeSessionId! : remote.sessions[0]!.id
          );
          clearLegacyChatSessionsStorage();
        } else {
          const legacy = loadChatSessionsFile();
          if (legacy && legacy.sessions.length > 0) {
            await putChatSessionsState(legacy);
            if (cancelled) return;
            clearLegacyChatSessionsStorage();
            setSessions(legacy.sessions);
            setActiveSessionId(legacy.activeSessionId);
          } else {
            const s = createEmptySession();
            const initial: ChatSessionPersisted[] = [s];
            await putChatSessionsState({
              version: CHAT_SESSIONS_VERSION,
              activeSessionId: s.id,
              sessions: initial,
            });
            if (cancelled) return;
            setSessions(initial);
            setActiveSessionId(s.id);
          }
        }
      } catch (e) {
        if (!cancelled) {
          console.error(e);
          setError(
            e instanceof Error
              ? e.message
              : "无法从服务器加载会话，请确认后端已启动且 API 地址正确"
          );
          const s = createEmptySession();
          setSessions([s]);
          setActiveSessionId(s.id);
        }
      } finally {
        if (!cancelled) {
          persistSkipRef.current = true;
          setSessionsReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionsReady || activeSessionId === null || sessions.length === 0) {
      return;
    }
    if (!sessions.some((s) => s.id === activeSessionId)) {
      return;
    }
    if (persistSkipRef.current) {
      persistSkipRef.current = false;
      return;
    }
    if (persistTimerRef.current) clearTimeout(persistTimerRef.current);
    persistTimerRef.current = setTimeout(() => {
      persistTimerRef.current = null;
      void putChatSessionsState({
        version: CHAT_SESSIONS_VERSION,
        activeSessionId,
        sessions,
      }).catch((err) => {
        console.error("chat sessions persist", err);
      });
    }, 450);
    return () => {
      if (persistTimerRef.current) {
        clearTimeout(persistTimerRef.current);
        persistTimerRef.current = null;
      }
    };
  }, [sessions, activeSessionId, sessionsReady]);

  const sessionView = useMemo(() => {
    const active = sessions.find((s) => s.id === activeSessionId) ?? null;
    return {
      messages: active?.messages ?? [],
      lastEvidenceEntries: active?.lastEvidenceEntries ?? [],
      lastCitations: active?.lastCitations ?? [],
    };
  }, [sessions, activeSessionId]);

  const sessionsSorted = useMemo(
    () => [...sessions].sort((a, b) => b.updatedAt - a.updatedAt),
    [sessions]
  );

  const resetEphemeral = useCallback(() => {
    thinkingRef.current = "";
    assistantRef.current = "";
    setThinkingBuffer("");
    setAssistantBuffer("");
    setStreamingCitations([]);
    setTraceLines([]);
    setSubAgents([]);
    setError(null);
    setActiveChunkId(null);
  }, []);

  useEffect(() => {
    if (!sessionsReady || sessions.length === 0) return;
    const valid =
      activeSessionId !== null &&
      sessions.some((s) => s.id === activeSessionId);
    if (!valid) {
      const first = sessions[0]!;
      resetEphemeral();
      setStatus("idle");
      setActiveSessionId(first.id);
    }
  }, [sessions, activeSessionId, sessionsReady, resetEphemeral]);

  const createSession = useCallback(() => {
    if (status === "connecting" || status === "streaming") return;
    const s = createEmptySession();
    activeSessionIdRef.current = s.id;
    streamingSessionIdRef.current = null;
    activeRequestIdRef.current = null;
    setSessions((prev) => [s, ...prev]);
    setActiveSessionId(s.id);
    resetEphemeral();
    setStatus("idle");
  }, [resetEphemeral, status]);

  const selectSession = useCallback(
    (id: string) => {
      if (status === "connecting" || status === "streaming") return;
      if (!sessions.some((s) => s.id === id)) return;
      activeSessionIdRef.current = id;
      streamingSessionIdRef.current = null;
      activeRequestIdRef.current = null;
      setActiveSessionId(id);
      resetEphemeral();
      setStatus("idle");
    },
    [resetEphemeral, sessions, status]
  );

  const deleteSession = useCallback(
    (id: string) => {
      if (status === "connecting" || status === "streaming") return;
      setSessions((prev) => {
        if (prev.length <= 1) {
          return [createEmptySession()];
        }
        return prev.filter((s) => s.id !== id);
      });
    },
    [status]
  );

  const appendTrace = useCallback((type: string, detail: string) => {
    setTraceLines((prev) => [...prev.slice(-200), { type, detail }]);
  }, []);

  const sendQuery = useCallback(
    (query: string) => {
      const q = query.trim();
      if (!q) return;
      const prevWs = wsRef.current;
      if (prevWs) {
        try {
          prevWs.close();
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
      streamingSessionIdRef.current = null;
      activeRequestIdRef.current = null;

      const sid = activeSessionIdRef.current;
      if (!sid) return;

      const clientRequestId = `req_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
      streamingSessionIdRef.current = sid;
      activeRequestIdRef.current = clientRequestId;
      thinkingRef.current = "";
      assistantRef.current = "";
      setError(null);
      setThinkingBuffer("");
      setAssistantBuffer("");
      setStreamingCitations([]);
      setTraceLines([]);
      setSubAgents([]);
      setActiveChunkId(null);
      setStatus("connecting");

      const userId = `u_${Date.now()}`;
      const userMsg: ChatMessage = { id: userId, role: "user", content: q };

      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== sid) return s;
          const nextTitle =
            s.title === "新会话" && s.messages.length === 0
              ? titleFromFirstQuery(q)
              : s.title;
          return {
            ...s,
            title: nextTitle,
            updatedAt: Date.now(),
            messages: [...s.messages, userMsg],
            lastEvidenceEntries: [],
            lastCitations: [],
          };
        })
      );

      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("streaming");
        ws.send(
          JSON.stringify({
            type: "chat.start",
            client_request_id: clientRequestId,
            session_id: sid,
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
        if (t.startsWith("chat.")) {
          const expected = activeRequestIdRef.current;
          const incoming = data.client_request_id;
          if (
            expected == null ||
            typeof incoming !== "string" ||
            incoming !== expected
          ) {
            return;
          }
        }

        if (t === "chat.citation_context") {
          const p = readWsPayload(data);
          const citations = parseList<CitationDTO>(p.citations);
          const evidenceEntries = parseList<EvidenceEntryDTO>(
            p.evidence_entries
          );
          setStreamingCitations(citations);
          const streamSid = streamingSessionIdRef.current;
          if (streamSid) {
            setSessions((prev) =>
              prev.map((s) =>
                s.id === streamSid
                  ? {
                      ...s,
                      updatedAt: Date.now(),
                      lastCitations: citations,
                      lastEvidenceEntries: evidenceEntries,
                    }
                  : s
              )
            );
          }
          return;
        }

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
          const streamSid = streamingSessionIdRef.current;
          streamingSessionIdRef.current = null;
          activeRequestIdRef.current = null;

          const answer = normalizeAnswerText(data.answer);
          const rawFinal = assistantRef.current || answer;
          const finalText = stripEmbeddedThinkingBlock(
            stripLegacyCitationsAppendix(rawFinal)
          );
          const serverThink =
            typeof data.thinking === "string" ? data.thinking.trim() : "";
          const think =
            serverThink || thinkingRef.current.trim() || undefined;
          const citations = parseList<CitationDTO>(data.citations);
          const evidenceEntries = parseList<EvidenceEntryDTO>(
            data.evidence_entries
          );

          const assistantMsg: ChatMessage = {
            id: `a_${Date.now()}`,
            role: "assistant",
            content: finalText,
            thinking: think || undefined,
            citations: citations.length ? citations : undefined,
            evidenceEntries: evidenceEntries.length
              ? evidenceEntries
              : undefined,
          };

          if (streamSid) {
            setSessions((prev) =>
              prev.map((s) =>
                s.id === streamSid
                  ? {
                      ...s,
                      updatedAt: Date.now(),
                      messages: [...s.messages, assistantMsg],
                      lastEvidenceEntries: evidenceEntries,
                      lastCitations: citations,
                    }
                  : s
              )
            );
          }

          assistantRef.current = "";
          thinkingRef.current = "";
          setAssistantBuffer("");
          setThinkingBuffer("");
          setStreamingCitations([]);
          setStatus("done");
          ws.close();
          return;
        }

        if (t === "chat.failed") {
          streamingSessionIdRef.current = null;
          activeRequestIdRef.current = null;
          setStreamingCitations([]);
          const msg =
            (data.error as { message?: string } | undefined)?.message ??
            "unknown error";
          setError(msg);
          setStatus("error");
          ws.close();
        }
      };

      ws.onerror = () => {
        streamingSessionIdRef.current = null;
        activeRequestIdRef.current = null;
        setStreamingCitations([]);
        setError("WebSocket error");
        setStatus("error");
      };

      ws.onclose = () => {
        wsRef.current = null;
      };
    },
    [appendTrace]
  );

  const stopGeneration = useCallback(() => {
    const ws = wsRef.current;
    const req = activeRequestIdRef.current;

    if (ws && ws.readyState === WebSocket.CONNECTING) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
      streamingSessionIdRef.current = null;
      activeRequestIdRef.current = null;
      resetEphemeral();
      setStatus("idle");
      return;
    }

    if (ws && ws.readyState === WebSocket.OPEN && req) {
      try {
        ws.send(
          JSON.stringify({ type: "chat.stop", client_request_id: req })
        );
      } catch {
        /* ignore */
      }
    }
  }, [resetEphemeral]);

  const clearMessages = useCallback(() => {
    const sid = activeSessionId;
    if (!sid) return;
    const w = wsRef.current;
    if (w) {
      try {
        w.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    }
    streamingSessionIdRef.current = null;
    activeRequestIdRef.current = null;
    setSessions((prev) =>
      prev.map((s) =>
        s.id === sid
          ? {
              ...s,
              title: "新会话",
              messages: [],
              lastEvidenceEntries: [],
              lastCitations: [],
              updatedAt: Date.now(),
            }
          : s
      )
    );
    resetEphemeral();
    setStatus("idle");
  }, [activeSessionId, resetEphemeral]);

  const value = useMemo(
    () => ({
      sessionsReady,
      sessions: sessionsSorted,
      activeSessionId,
      createSession,
      selectSession,
      deleteSession,
      messages: sessionView.messages,
      sendQuery,
      stopGeneration,
      status,
      error,
      thinkingBuffer,
      assistantBuffer,
      traceLines,
      subAgents,
      clearMessages,
      lastEvidenceEntries: sessionView.lastEvidenceEntries,
      lastCitations: sessionView.lastCitations,
      streamingCitations,
      activeChunkId,
      setActiveChunkId,
    }),
    [
      sessionsReady,
      sessionsSorted,
      activeSessionId,
      createSession,
      selectSession,
      deleteSession,
      sessionView,
      sendQuery,
      stopGeneration,
      status,
      error,
      thinkingBuffer,
      assistantBuffer,
      traceLines,
      subAgents,
      clearMessages,
      activeChunkId,
      streamingCitations,
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
