"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type TextareaHTMLAttributes,
} from "react";
import {
  fetchAgentTemplates,
  subscribeAgentTemplatesReload,
  type AgentTemplateItem,
} from "@/lib/agentTemplatesApi";
import styles from "./AgentChatComposer.module.css";

const DEFAULT_MAX_PINNED = 12;

export type AgentChatComposerProps = Omit<
  TextareaHTMLAttributes<HTMLTextAreaElement>,
  "onChange" | "value"
> & {
  text: string;
  onTextChange: (next: string) => void;
  pinnedAgentIds: string[];
  onPinnedAgentIdsChange: (next: string[]) => void;
  /** 与后端 max_templates_per_role 对齐时可传入；默认 12 */
  maxPinnedAgents?: number;
  /** 连接中或流式生成中：右下角主按钮为「停止」 */
  isGenerating: boolean;
  sessionsReady: boolean;
  /** 有芯片或正文时可提交发送 */
  canSubmit: boolean;
  onStop: () => void;
};

/** 填充纸飞机，小尺寸下在圆形按钮内更清晰 */
function IconPaperPlane({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width={17}
      height={17}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path d="M2 21 22 12 2 3v6.98L14.03 12 2 15.02V21z" />
    </svg>
  );
}

function IconStopSquare({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      width={18}
      height={18}
      viewBox="0 0 24 24"
      fill="currentColor"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <rect x={7} y={7} width={10} height={10} rx={2} />
    </svg>
  );
}

function getMentionAtCursor(
  text: string,
  cursor: number
): { start: number; query: string } | null {
  const before = text.slice(0, cursor);
  const at = before.lastIndexOf("@");
  if (at < 0) return null;
  const afterAt = before.slice(at + 1);
  if (/[\s\n]/.test(afterAt)) return null;
  return { start: at, query: afterAt };
}

export function AgentChatComposer({
  text: textValue,
  onTextChange,
  pinnedAgentIds,
  onPinnedAgentIdsChange,
  maxPinnedAgents = DEFAULT_MAX_PINNED,
  isGenerating,
  sessionsReady,
  canSubmit,
  onStop,
  className: _omitClass,
  onKeyDown,
  ...rest
}: AgentChatComposerProps) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [catalog, setCatalog] = useState<AgentTemplateItem[]>([]);
  const [agentsError, setAgentsError] = useState<string | null>(null);
  const [agentsLoading, setAgentsLoading] = useState(true);
  const [mention, setMention] = useState<{ start: number; query: string } | null>(
    null
  );
  const [activeIdx, setActiveIdx] = useState(0);
  const [suppressDrop, setSuppressDrop] = useState(false);

  const blurbById = useMemo(() => {
    const m = new Map<string, string>();
    for (const a of catalog) m.set(a.id, a.blurb);
    return m;
  }, [catalog]);

  const loadAgents = useCallback(() => {
    setAgentsLoading(true);
    setAgentsError(null);
    fetchAgentTemplates()
      .then(setCatalog)
      .catch((e: unknown) => {
        setCatalog([]);
        setAgentsError(e instanceof Error ? e.message : "加载失败");
      })
      .finally(() => setAgentsLoading(false));
  }, []);

  useEffect(() => {
    loadAgents();
    return subscribeAgentTemplatesReload(loadAgents);
  }, [loadAgents]);

  const mentionKey = mention ? `${mention.start}:${mention.query}` : "";
  const prevMentionKey = useRef<string>("__init__");
  useEffect(() => {
    if (mentionKey === prevMentionKey.current) return;
    prevMentionKey.current = mentionKey;
    setActiveIdx(0);
    if (mention) setSuppressDrop(false);
  }, [mentionKey, mention]);

  const updateMentionForCursor = useCallback((text: string, cursor: number) => {
    const m = getMentionAtCursor(text, cursor);
    setMention((prev) => {
      if (
        prev &&
        m &&
        prev.start === m.start &&
        prev.query === m.query
      ) {
        return prev;
      }
      return m ?? null;
    });
  }, []);

  const filtered = useMemo(() => {
    if (!mention || catalog.length === 0) return [];
    const q = mention.query.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.filter(
      (a) =>
        a.id.toLowerCase().startsWith(q) ||
        a.blurb.toLowerCase().includes(q)
    );
  }, [catalog, mention]);

  const atPickLimit = pinnedAgentIds.length >= maxPinnedAgents;
  const showPanel = Boolean(mention) && !suppressDrop;
  const listInteractive =
    !agentsLoading &&
    !agentsError &&
    catalog.length > 0 &&
    filtered.length > 0 &&
    !atPickLimit;

  const clampedIdx =
    filtered.length > 0 ? Math.min(activeIdx, filtered.length - 1) : 0;

  useEffect(() => {
    setActiveIdx((i) =>
      filtered.length === 0 ? 0 : Math.min(i, filtered.length - 1)
    );
  }, [filtered.length]);

  useLayoutEffect(() => {
    if (!listInteractive || !dropdownRef.current) return;
    const root = dropdownRef.current;
    const buttons = root.querySelectorAll<HTMLButtonElement>("button[role='option']");
    const el = buttons[clampedIdx];
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [clampedIdx, listInteractive, filtered]);

  const removeChip = useCallback(
    (id: string) => {
      onPinnedAgentIdsChange(pinnedAgentIds.filter((x) => x !== id));
    },
    [pinnedAgentIds, onPinnedAgentIdsChange]
  );

  const insertMention = useCallback(
    (id: string) => {
      const el = taRef.current;
      if (!el || mention === null) return;
      const cursor = el.selectionStart ?? textValue.length;
      const start = mention.start;
      const nextText = textValue.slice(0, start) + textValue.slice(cursor);
      onTextChange(nextText);
      if (!pinnedAgentIds.includes(id) && pinnedAgentIds.length < maxPinnedAgents) {
        onPinnedAgentIdsChange([...pinnedAgentIds, id]);
      }
      queueMicrotask(() => {
        el.focus();
        el.setSelectionRange(start, start);
      });
      setMention(null);
      setSuppressDrop(false);
    },
    [
      mention,
      onTextChange,
      textValue,
      pinnedAgentIds,
      onPinnedAgentIdsChange,
      maxPinnedAgents,
    ]
  );

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (listInteractive) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        insertMention(filtered[clampedIdx]!.id);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setSuppressDrop(true);
        return;
      }
    }

    if (e.key === "Backspace") {
      const el = taRef.current;
      const pos = el?.selectionStart ?? 0;
      const end = el?.selectionEnd ?? 0;
      if (
        textValue === "" &&
        pos === 0 &&
        end === 0 &&
        pinnedAgentIds.length > 0
      ) {
        e.preventDefault();
        onPinnedAgentIdsChange(pinnedAgentIds.slice(0, -1));
        return;
      }
    }

    onKeyDown?.(e);
  };

  const hasChips = pinnedAgentIds.length > 0;

  return (
    <div className={styles.wrap}>
      {showPanel ? (
        <div
          ref={dropdownRef}
          className={styles.dropdown}
          role="listbox"
          aria-label="Agent 模板"
        >
          {agentsLoading ? (
            <div className={styles.hint}>加载 Agent 列表…</div>
          ) : agentsError ? (
            <div className={styles.hint}>{agentsError}</div>
          ) : catalog.length === 0 ? (
            <div className={styles.hint}>暂无 prompts/*.agent.md 模板</div>
          ) : filtered.length === 0 ? (
            <div className={styles.hint}>无匹配项，继续输入或空格结束</div>
          ) : atPickLimit ? (
            <div className={styles.hint}>
              已达上限（{maxPinnedAgents} 个），请先移除芯片再添加
            </div>
          ) : (
            filtered.map((a, i) => (
              <button
                key={a.id}
                type="button"
                role="option"
                aria-selected={i === clampedIdx}
                className={
                  i === clampedIdx ? `${styles.item} ${styles.itemActive}` : styles.item
                }
                onMouseDown={(ev) => {
                  ev.preventDefault();
                  insertMention(a.id);
                }}
                onMouseEnter={() => setActiveIdx(i)}
              >
                <span className={styles.id}>@{a.id}</span>
                <span className={styles.blurb}>{a.blurb || "—"}</span>
              </button>
            ))
          )}
        </div>
      ) : null}
      <div className={styles.shell}>
        {hasChips ? (
          <div className={styles.chips} aria-label="已选 Agent 模板">
            {pinnedAgentIds.map((id) => (
              <div
                key={id}
                className={styles.chip}
                title={blurbById.get(id) || id}
              >
                <span className={styles.chipMain}>
                  <span className={styles.chipAt}>@</span>
                  <span className={styles.chipId}>{id}</span>
                </span>
                <button
                  type="button"
                  className={styles.chipRemove}
                  aria-label={`移除 ${id}`}
                  onClick={() => removeChip(id)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        ) : null}
        <div className={styles.inputRow}>
          <div className={styles.textareaGrow}>
            <textarea
              ref={taRef}
              {...rest}
              className={styles.textarea}
              value={textValue}
              onChange={(e) => {
                const text = e.target.value;
                onTextChange(text);
                queueMicrotask(() => {
                  const el = taRef.current;
                  if (!el) return;
                  const cursor = el.selectionStart ?? text.length;
                  updateMentionForCursor(text, cursor);
                });
              }}
              onKeyDown={handleKeyDown}
              onClick={(e) => {
                const el = e.currentTarget;
                updateMentionForCursor(
                  textValue,
                  el.selectionStart ?? textValue.length
                );
              }}
              onSelect={(e) => {
                const el = e.currentTarget;
                updateMentionForCursor(
                  textValue,
                  el.selectionStart ?? textValue.length
                );
              }}
            />
          </div>
          {isGenerating ? (
            <button
              type="button"
              className={`${styles.actionBtn} ${styles.actionBtnStop}`}
              onClick={onStop}
              title="停止生成"
              aria-label="停止生成"
            >
              <IconStopSquare className={styles.actionIcon} />
            </button>
          ) : (
            <button
              type="submit"
              className={`${styles.actionBtn} ${styles.actionBtnSend}`}
              disabled={!sessionsReady || !canSubmit}
              title="发送"
              aria-label="发送"
            >
              <IconPaperPlane className={styles.actionIcon} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** 将芯片与正文拼成后端可解析的一条 query */
export function composeChatQuery(
  pinnedAgentIds: string[],
  text: string
): string {
  const parts = pinnedAgentIds.map((id) => `@${id}`);
  const body = text.trim();
  if (body) parts.push(body);
  return parts.join(" ").trim();
}
