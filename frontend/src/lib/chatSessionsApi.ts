import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export class ChatSessionsConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatSessionsConflictError";
  }
}

export async function fetchChatSessionsState(): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new Error(`加载会话失败: HTTP ${r.status}`);
  }
  return r.json() as Promise<ChatSessionsFile>;
}

export async function putChatSessionsState(
  body: ChatSessionsFile
): Promise<{ ok: true; stateRevision: number }> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    if (r.status === 409) {
      throw new ChatSessionsConflictError(
        `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
      );
    }
    throw new Error(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
    );
  }
  return r.json() as Promise<{ ok: true; stateRevision: number }>;
}
