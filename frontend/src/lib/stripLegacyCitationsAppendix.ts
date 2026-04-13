/** 旧版后端在文末追加的 Citations 块；历史 localStorage 消息可能仍带此后缀 */
const LEGACY_CITATIONS_MARKER = "\n---\nCitations:";

/** 旧版流式把 thinking 拼进正文（--- Thinking --- … --- /Thinking ---） */
const EMBEDDED_THINKING_BLOCK =
  /---\s*Thinking\s*---[\s\S]*?---\s*\/Thinking\s*---\s*/gi;

export function stripLegacyCitationsAppendix(s: string): string {
  const i = s.indexOf(LEGACY_CITATIONS_MARKER);
  return i >= 0 ? s.slice(0, i).trimEnd() : s;
}

/** 从正文去掉内嵌的 Thinking 块（无单独 thinking 字段的旧消息） */
export function stripEmbeddedThinkingBlock(s: string): string {
  return s.replace(EMBEDDED_THINKING_BLOCK, "").trimStart();
}
