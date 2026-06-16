import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export class ChatSessionsApiError extends Error {
  status: number;
  code: string | null;
  currentRevision: number | null;

  constructor(message: string, status: number, code: string | null, currentRevision: number | null) {
    super(message);
    this.name = "ChatSessionsApiError";
    this.status = status;
    this.code = code;
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

export async function putChatSessionsState(body: ChatSessionsFile): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    let code: string | null = null;
    let currentRevision: number | null = null;
    try {
      const parsed = JSON.parse(t) as {
        error?: { code?: unknown; detail?: { currentRevision?: unknown } };
      };
      code = typeof parsed.error?.code === "string" ? parsed.error.code : null;
      const rawRevision = parsed.error?.detail?.currentRevision;
      currentRevision = typeof rawRevision === "number" ? rawRevision : null;
    } catch {
      /* keep raw text in the message below */
    }
    throw new ChatSessionsApiError(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`,
      r.status,
      code,
      currentRevision
    );
  }
  return r.json() as Promise<ChatSessionsFile>;
}
