"use client";

import { useEffect } from "react";
import type {
  CitationDTO,
  EvidenceEntryDTO,
  SubAgentRun,
} from "@/types/chat";
import type { TraceLine } from "@/stores/ChatProvider";
import styles from "./EvidencePanel.module.css";

function subAgentStatusLabel(s: SubAgentRun["status"]): string {
  if (s === "running") return "运行中";
  if (s === "completed") return "已完成";
  return "失败";
}

export function EvidencePanel(props: {
  traceLines: TraceLine[];
  subAgents: SubAgentRun[];
  thinking?: string;
  streaming?: boolean;
  evidenceEntries: EvidenceEntryDTO[];
  citations: CitationDTO[];
  activeChunkId: string | null;
  onSelectCitation: (chunkId: string) => void;
}) {
  const {
    traceLines,
    subAgents,
    thinking,
    streaming,
    evidenceEntries,
    citations,
    activeChunkId,
    onSelectCitation,
  } = props;

  useEffect(() => {
    if (!activeChunkId) return;
    const el = document.getElementById(`evidence-${activeChunkId}`);
    el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeChunkId]);

  return (
    <aside className={styles.panel} aria-label="检索、子智能体与工具追踪">
      <h2 className={styles.title}>Evidence &amp; citations</h2>

      {citations.length > 0 ? (
        <section className={styles.block}>
          <h3 className={styles.sub}>Citations</h3>
          <p className={styles.hintSmall}>
            点击跳转到下方对应证据块（页码 / 定位摘要）。
          </p>
          <div className={styles.chips}>
            {citations.map((c, i) => (
              <button
                key={`${c.chunk_id}-${i}`}
                type="button"
                className={
                  activeChunkId === c.chunk_id ? styles.chipActive : styles.chip
                }
                onClick={() => onSelectCitation(c.chunk_id)}
              >
                [{i + 1}] {c.location_summary || c.chunk_id.slice(0, 8)}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      {evidenceEntries.length > 0 ? (
        <section className={styles.block}>
          <h3 className={styles.sub}>Evidence chunks</h3>
          <ul className={styles.evidenceList}>
            {evidenceEntries.map((e) => (
              <li
                key={e.chunk_id}
                id={`evidence-${e.chunk_id}`}
                className={
                  activeChunkId === e.chunk_id
                    ? styles.evidenceItemActive
                    : styles.evidenceItem
                }
              >
                <div className={styles.evidenceMeta}>
                  <span className={styles.mono}>{e.chunk_id.slice(0, 8)}…</span>
                  <span>{e.location_summary}</span>
                </div>
                {e.evidence_snippet_text_v1 ? (
                  <p className={styles.snippet}>{e.evidence_snippet_text_v1}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {thinking ? (
        <section className={styles.block}>
          <h3 className={styles.sub}>Thinking</h3>
          <pre className={styles.pre}>{thinking}</pre>
        </section>
      ) : null}
      {subAgents.length > 0 ? (
        <section className={styles.block} aria-label="子智能体">
          <h3 className={styles.sub}>子智能体</h3>
          <p className={styles.hintSmall}>
            Orchestrator 派生的子任务实例（WebSocket：chat.agent_*）。
          </p>
          <ul className={styles.subAgentList}>
            {subAgents.map((a) => (
              <li key={a.agent_id} className={styles.subAgentCard}>
                <div className={styles.subAgentHead}>
                  <span className={styles.mono}>{a.agent_id}</span>
                  <span
                    className={
                      a.status === "failed"
                        ? styles.subAgentBadgeFail
                        : a.status === "completed"
                          ? styles.subAgentBadgeOk
                          : styles.subAgentBadgeRun
                    }
                  >
                    {subAgentStatusLabel(a.status)}
                  </span>
                </div>
                {a.profile_id ? (
                  <p className={styles.subAgentMeta}>
                    profile:{" "}
                    <span className={styles.mono}>{a.profile_id}</span>
                  </p>
                ) : null}
                {a.task_summary ? (
                  <p className={styles.subAgentTask}>{a.task_summary}</p>
                ) : null}
                {a.lastProgress ? (
                  <pre className={styles.subAgentPre}>{a.lastProgress}</pre>
                ) : null}
                {a.outputSummary ? (
                  <p className={styles.subAgentOut}>{a.outputSummary}</p>
                ) : null}
                {a.errorMessage ? (
                  <p className={styles.subAgentErr} role="alert">
                    {a.errorMessage}
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {streaming ? (
        <p className={styles.hint}>流式生成中…</p>
      ) : null}
      <section className={styles.block}>
        <h3 className={styles.sub}>Trace</h3>
        <ul className={styles.list}>
          {traceLines.length === 0 ? (
            <li className={styles.muted}>暂无 trace</li>
          ) : (
            traceLines.map((line, i) => (
              <li key={`${line.type}-${i}`} className={styles.item}>
                <span className={styles.tag}>{line.type}</span>
                <span className={styles.detail}>{line.detail}</span>
              </li>
            ))
          )}
        </ul>
      </section>
    </aside>
  );
}
