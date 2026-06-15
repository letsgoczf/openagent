import { apiBase } from "@/lib/api";
import type {
  ChatSessionsPutBody,
  ChatSessionsSaveResult,
  ChatSessionsState,
} from "@/lib/chatSessionPersistence";

export class ChatSessionsConflictError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ChatSessionsConflictError";
  }
}

export async function fetchChatSessionsState(): Promise<ChatSessionsState> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new Error(`加载会话失败: HTTP ${r.status}`);
  }
  return r.json() as Promise<ChatSessionsState>;
}

export async function putChatSessionsState(
  body: ChatSessionsPutBody
): Promise<ChatSessionsSaveResult> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    if (r.status === 409) {
      throw new ChatSessionsConflictError("会话已在其它窗口更新，请合并后重试");
    }
    throw new Error(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
    );
  }
  return r.json() as Promise<ChatSessionsSaveResult>;
}
