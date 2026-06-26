import { apiBase } from "@/lib/api";
import type {
  ChatSessionsFile,
  ChatSessionsRemoteFile,
} from "@/lib/chatSessionPersistence";

export class ChatSessionsConflictError extends Error {
  constructor() {
    super("chat session state conflict");
  }
}

export interface PutChatSessionsResponse {
  ok: boolean;
  stateRevision: number;
}

export async function fetchChatSessionsState(): Promise<ChatSessionsRemoteFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new Error(`加载会话失败: HTTP ${r.status}`);
  }
  return r.json() as Promise<ChatSessionsRemoteFile>;
}

export async function putChatSessionsState(
  body: ChatSessionsFile & { baseRevision: number },
  init?: RequestInit
): Promise<PutChatSessionsResponse> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    ...init,
    method: "PUT",
    headers,
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    if (r.status === 409) {
      throw new ChatSessionsConflictError();
    }
    const t = await r.text().catch(() => "");
    throw new Error(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
    );
  }
  return r.json() as Promise<PutChatSessionsResponse>;
}
