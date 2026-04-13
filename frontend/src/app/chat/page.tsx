"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { CitationInlineText } from "@/components/chat/CitationInlineText";
import {
  stripEmbeddedThinkingBlock,
  stripLegacyCitationsAppendix,
} from "@/lib/stripLegacyCitationsAppendix";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import {
  AgentChatComposer,
  composeChatQuery,
} from "@/components/chat/AgentChatComposer";
import { useChat } from "@/hooks/useChat";
import { useScrollbarReveal } from "@/hooks/useScrollbarReveal";
import styles from "./chat.module.css";

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [pinnedAgents, setPinnedAgents] = useState<string[]>([]);
  const [multiMode, setMultiMode] = useState(false);
  const MULTI_MODE_STORAGE_KEY = "openagent.chat.multiMode";
  const {
    sessionsReady,
    sessions,
    activeSessionId,
    createSession,
    selectSession,
    deleteSession,
    messages,
    sendQuery,
    stopGeneration,
    status,
    error,
    thinkingBuffer,
    assistantBuffer,
    traceLines,
    subAgents,
    clearMessages,
    lastEvidenceEntries,
    lastCitations,
    streamingCitations,
    activeChunkId,
    setActiveChunkId,
  } = useChat();

  const streaming = status === "streaming" || status === "connecting";
  const hasComposerContent =
    pinnedAgents.length > 0 || input.trim().length > 0;

  const messagesScrollRef = useRef<HTMLDivElement>(null);
  const sessionListRef = useRef<HTMLUListElement>(null);
  const evidenceColumnRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  useScrollbarReveal(messagesScrollRef, styles.scrollbarReveal);
  useScrollbarReveal(sessionListRef, styles.scrollbarReveal, {
    enabled: sessionsReady,
  });
  useScrollbarReveal(evidenceColumnRef, styles.scrollbarReveal);

  const scrollMessagesIfPinned = useCallback(() => {
    const el = messagesScrollRef.current;
    if (!el) return;
    const threshold = 96;
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    if (stickToBottomRef.current || nearBottom) {
      el.scrollTop = el.scrollHeight;
    }
  }, []);

  useEffect(() => {
    scrollMessagesIfPinned();
  }, [messages, assistantBuffer, streaming, scrollMessagesIfPinned]);

  useEffect(() => {
    stickToBottomRef.current = true;
    const id = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const el = messagesScrollRef.current;
        if (el) el.scrollTop = el.scrollHeight;
      });
    });
    return () => cancelAnimationFrame(id);
  }, [activeSessionId]);

  const onMessagesScroll = useCallback(() => {
    const el = messagesScrollRef.current;
    if (!el) return;
    const threshold = 80;
    stickToBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(MULTI_MODE_STORAGE_KEY);
    if (raw === "1") setMultiMode(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(MULTI_MODE_STORAGE_KEY, multiMode ? "1" : "0");
  }, [multiMode]);

  return (
    <div className={styles.layout}>
      <header className={styles.top}>
        <Link href="/" className={styles.back}>
          ← Home
        </Link>
        <h1 className={styles.title}>Chat</h1>
        <nav className={styles.navMini} aria-label="Section">
          <Link href="/documents">Documents</Link>
          <Link href="/settings">Settings</Link>
        </nav>
        <button
          type="button"
          className={styles.clear}
          onClick={clearMessages}
          disabled={streaming || !sessionsReady}
        >
          清空当前会话
        </button>
      </header>
      <div className={styles.grid}>
        <aside className={styles.sessionRail} aria-label="历史会话">
          <div className={styles.sessionRailHead}>
            <span className={styles.sessionRailTitle}>会话</span>
            <button
              type="button"
              className={styles.newSession}
              onClick={createSession}
              disabled={!sessionsReady || streaming}
            >
              新建
            </button>
          </div>
          {!sessionsReady ? (
            <p className={styles.sessionHint}>加载中…</p>
          ) : (
            <ul
              ref={sessionListRef}
              className={`${styles.sessionList} ${styles.scrollbarAutoHide}`}
            >
              {sessions.map((s) => {
                const active = s.id === activeSessionId;
                return (
                  <li key={s.id}>
                    <div className={styles.sessionRow}>
                      <button
                        type="button"
                        className={
                          active ? styles.sessionItemActive : styles.sessionItem
                        }
                        onClick={() => selectSession(s.id)}
                        disabled={streaming}
                        title={s.title}
                      >
                        <span className={styles.sessionTitle}>{s.title}</span>
                        <span className={styles.sessionMeta}>
                          {s.messages.length} 条
                        </span>
                      </button>
                      <button
                        type="button"
                        className={styles.sessionDelete}
                        onClick={() => deleteSession(s.id)}
                        disabled={streaming}
                        aria-label={`删除会话 ${s.title}`}
                      >
                        ×
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>
        <section className={styles.thread} aria-label="对话">
          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
          <div
            ref={messagesScrollRef}
            className={`${styles.messagesScroll} ${styles.scrollbarAutoHide}`}
            onScroll={onMessagesScroll}
            role="log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label="对话消息"
          >
            <ul className={styles.messages}>
            {messages.map((m) => (
              <li
                key={m.id}
                className={
                  m.role === "user" ? styles.msgUser : styles.msgAssistant
                }
              >
                <span className={styles.role}>{m.role}</span>
                {m.thinking ? (
                  <details className={styles.think}>
                    <summary>Thinking</summary>
                    <pre>{m.thinking}</pre>
                  </details>
                ) : null}
                <div className={styles.bubble}>
                  {m.role === "assistant" ? (
                    <CitationInlineText
                      text={stripEmbeddedThinkingBlock(
                        stripLegacyCitationsAppendix(m.content)
                      )}
                      citations={m.citations}
                      onCiteClick={(id) => setActiveChunkId(id)}
                    />
                  ) : (
                    m.content
                  )}
                </div>
              </li>
            ))}
            {streaming && assistantBuffer ? (
              <li className={styles.msgAssistant}>
                <span className={styles.role}>assistant</span>
                <div className={styles.bubbleDim}>
                  <CitationInlineText
                    text={stripLegacyCitationsAppendix(assistantBuffer)}
                    citations={
                      streamingCitations.length
                        ? streamingCitations
                        : undefined
                    }
                    onCiteClick={(id) => setActiveChunkId(id)}
                  />
                </div>
              </li>
            ) : null}
            </ul>
          </div>
          <form
            className={styles.form}
            onSubmit={(e) => {
              e.preventDefault();
              if (!streaming && sessionsReady) {
                const combined = composeChatQuery(pinnedAgents, input);
                const raw = combined.trim();
                const trigger = "[multi]";
                const normalized = raw.startsWith(trigger)
                  ? raw.slice(trigger.length).trim()
                  : raw;
                const finalQuery = multiMode
                  ? `${trigger} ${normalized}`.trim()
                  : normalized;
                sendQuery(finalQuery);
                setInput("");
                setPinnedAgents([]);
              }
            }}
          >
            <label className={styles.label} htmlFor="q">
              消息
            </label>
            <label className={styles.multiToggle}>
              <input
                type="checkbox"
                checked={multiMode}
                onChange={(e) => setMultiMode(e.target.checked)}
                disabled={streaming || !sessionsReady}
              />
              多智能体协同
            </label>
            <AgentChatComposer
              id="q"
              rows={3}
              text={input}
              onTextChange={setInput}
              pinnedAgentIds={pinnedAgents}
              onPinnedAgentIdsChange={setPinnedAgents}
              isGenerating={streaming}
              sessionsReady={sessionsReady}
              canSubmit={hasComposerContent}
              onStop={stopGeneration}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                if (e.shiftKey) return;
                if (e.nativeEvent.isComposing) return;
                e.preventDefault();
                if (streaming || !sessionsReady || !hasComposerContent) return;
                e.currentTarget.form?.requestSubmit();
              }}
              placeholder="输入 @ 添加 Agent；Enter 发送 · Shift+Enter 换行 · 右下角纸飞机发送 / 方块停止"
              disabled={streaming || !sessionsReady}
            />
          </form>
        </section>
        <div
          ref={evidenceColumnRef}
          className={`${styles.evidenceColumn} ${styles.scrollbarAutoHide}`}
        >
          <EvidencePanel
            className={styles.evidenceInColumn}
            variant="floating"
            traceLines={traceLines}
            subAgents={subAgents}
            thinking={streaming ? thinkingBuffer : undefined}
            streaming={streaming}
            evidenceEntries={lastEvidenceEntries}
            citations={lastCitations}
            activeChunkId={activeChunkId}
            onSelectCitation={setActiveChunkId}
          />
        </div>
      </div>
    </div>
  );
}
