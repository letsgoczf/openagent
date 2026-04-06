/** 从 WS JSON 中安全取出 payload 对象 */

export function readWsPayload(data: Record<string, unknown>): Record<string, unknown> {
  const p = data.payload;
  if (p && typeof p === "object" && !Array.isArray(p)) {
    return p as Record<string, unknown>;
  }
  return {};
}

export function subAgentTaskSummary(p: Record<string, unknown>): string | undefined {
  const v =
    p.task_summary ?? p.subtask ?? p.description ?? p.task ?? p.summary;
  if (v == null) return undefined;
  const s = String(v).trim();
  return s || undefined;
}
