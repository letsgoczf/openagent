import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export interface PutChatSessionsStateResult {
  ok: boolean;
  stateRevision: number;
}

export class ChatSessionsConflictError extends Error {
  currentRevision: number | null;

  constructor(message: string, currentRevision: number | null) {
    super(message);
    this.name = "ChatSessionsConflictError";
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

export async function putChatSessionsState(
  body: ChatSessionsFile
): Promise<PutChatSessionsStateResult> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    if (r.status === 409) {
      let currentRevision: number | null = null;
      try {
        const payload = JSON.parse(t) as {
          error?: { detail?: { currentRevision?: unknown }; message?: unknown };
        };
        const raw = payload.error?.detail?.currentRevision;
        currentRevision = typeof raw === "number" ? raw : null;
        throw new ChatSessionsConflictError(
          typeof payload.error?.message === "string"
            ? payload.error.message
            : "会话已在其他窗口更新",
          currentRevision
        );
      } catch (err) {
        if (err instanceof ChatSessionsConflictError) throw err;
      }
      throw new ChatSessionsConflictError("会话已在其他窗口更新", currentRevision);
    }
    throw new Error(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
    );
  }
  return r.json() as Promise<PutChatSessionsStateResult>;
}
