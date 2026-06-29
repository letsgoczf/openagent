import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export class ChatSessionsStateError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ChatSessionsStateError";
    this.status = status;
  }
}

export async function fetchChatSessionsState(): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new ChatSessionsStateError(`加载会话失败: HTTP ${r.status}`, r.status);
  }
  return r.json() as Promise<ChatSessionsFile>;
}

export async function putChatSessionsState(
  body: ChatSessionsFile
): Promise<{ stateRevision: number }> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new ChatSessionsStateError(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`,
      r.status
    );
  }
  return r.json() as Promise<{ stateRevision: number }>;
}
