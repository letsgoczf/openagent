import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export class ChatSessionsApiError extends Error {
  status: number;
  body: string;

  constructor(message: string, status: number, body: string) {
    super(message);
    this.name = "ChatSessionsApiError";
    this.status = status;
    this.body = body;
  }
}

export interface ChatSessionsSaveResult {
  ok: boolean;
  stateRevision: number;
}

export async function fetchChatSessionsState(): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new Error(`加载会话失败: HTTP ${r.status}`);
  }
  return r.json() as Promise<ChatSessionsFile>;
}

export function isChatSessionsConflictError(err: unknown): boolean {
  return err instanceof ChatSessionsApiError && err.status === 409;
}

export async function putChatSessionsState(
  body: ChatSessionsFile
): Promise<ChatSessionsSaveResult> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new ChatSessionsApiError(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`,
      r.status,
      t
    );
  }
  return r.json() as Promise<ChatSessionsSaveResult>;
}
