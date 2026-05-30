import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export class ChatSessionsApiError extends Error {
  status: number;
  currentRevision: number | null;

  constructor(message: string, status: number, currentRevision: number | null = null) {
    super(message);
    this.name = "ChatSessionsApiError";
    this.status = status;
    this.currentRevision = currentRevision;
  }
}

export async function fetchChatSessionsState(): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new Error(`加载会话失败: HTTP ${r.status}`);
  }
  return r.json() as Promise<ChatSessionsFile>;
}

export async function putChatSessionsState(body: ChatSessionsFile): Promise<number | null> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    let currentRevision: number | null = null;
    try {
      const data = JSON.parse(t) as {
        error?: { detail?: { currentRevision?: unknown } };
      };
      const rev = data.error?.detail?.currentRevision;
      currentRevision = typeof rev === "number" ? rev : null;
    } catch {
      /* response body may be plain text */
    }
    throw new ChatSessionsApiError(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`,
      r.status,
      currentRevision
    );
  }
  const data = (await r.json().catch(() => ({}))) as {
    stateRevision?: unknown;
  };
  return typeof data.stateRevision === "number" ? data.stateRevision : null;
}
