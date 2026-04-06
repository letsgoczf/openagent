"use client";

import Link from "next/link";
import { useState } from "react";
import { EvidencePanel } from "@/components/evidence/EvidencePanel";
import { useChat } from "@/hooks/useChat";
import styles from "./chat.module.css";

export default function ChatPage() {
  const [input, setInput] = useState("");
  const {
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
  } = useChat();

  const streaming = status === "streaming" || status === "connecting";

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
        <button type="button" className={styles.clear} onClick={clearMessages}>
          清空
        </button>
      </header>
      <div className={styles.grid}>
        <section className={styles.thread} aria-label="对话">
          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
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
                <div className={styles.bubble}>{m.content}</div>
                {m.role === "assistant" && m.citations?.length ? (
                  <div className={styles.cites} role="navigation">
                    {m.citations.map((c, i) => (
                      <button
                        key={`${m.id}-${c.chunk_id}-${i}`}
                        type="button"
                        className={styles.citeChip}
                        onClick={() => setActiveChunkId(c.chunk_id)}
                      >
                        [{i + 1}] {c.location_summary || c.chunk_id.slice(0, 8)}
                      </button>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
            {streaming && assistantBuffer ? (
              <li className={styles.msgAssistant}>
                <span className={styles.role}>assistant</span>
                <div className={styles.bubbleDim}>{assistantBuffer}</div>
              </li>
            ) : null}
          </ul>
          <form
            className={styles.form}
            onSubmit={(e) => {
              e.preventDefault();
              if (!streaming) {
                sendQuery(input);
                setInput("");
              }
            }}
          >
            <label className={styles.label} htmlFor="q">
              消息
            </label>
            <textarea
              id="q"
              className={styles.input}
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="输入问题…（多智能体：前缀 [multi] ，需后端已启动）"
              disabled={streaming}
            />
            <button
              type="submit"
              className={styles.submit}
              disabled={streaming || !input.trim()}
            >
              {streaming ? "生成中…" : "发送"}
            </button>
          </form>
        </section>
        <EvidencePanel
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
  );
}
