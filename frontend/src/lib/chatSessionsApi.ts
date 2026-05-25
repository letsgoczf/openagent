import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export class ChatSessionsApiError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message);
    this.name = "ChatSessionsApiError";
  }
}

export async function fetchChatSessionsState(): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new ChatSessionsApiError(`加载会话失败: HTTP ${r.status}`, r.status);
  }
  return r.json() as Promise<ChatSessionsFile>;
}

export async function putChatSessionsState(
  body: ChatSessionsFile
): Promise<{ revision: number }> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new ChatSessionsApiError(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`,
      r.status
    );
  }
  const data = (await r.json().catch(() => ({}))) as { revision?: unknown };
  return { revision: typeof data.revision === "number" ? data.revision : 0 };
}
