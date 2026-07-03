import { apiBase } from "@/lib/api";
import type {
  ChatSessionsFile,
  ChatSessionsPutFile,
} from "@/lib/chatSessionPersistence";

export class ChatSessionsConflictError extends Error {
  readonly status = 409;
  readonly stateRevision: number | null;

  constructor(message: string, stateRevision: number | null) {
    super(message);
    this.name = "ChatSessionsConflictError";
    this.stateRevision = stateRevision;
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

export async function putChatSessionsState(
  body: ChatSessionsPutFile
): Promise<ChatSessionsSaveResult> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    if (r.status === 409) {
      let stateRevision: number | null = null;
      try {
        const parsed = JSON.parse(t) as {
          error?: { detail?: { stateRevision?: unknown } };
        };
        const raw = parsed.error?.detail?.stateRevision;
        stateRevision = typeof raw === "number" ? raw : null;
      } catch {
        /* ignore malformed error payload */
      }
      throw new ChatSessionsConflictError(
        `保存会话失败: HTTP ${r.status}`,
        stateRevision
      );
    }
    throw new Error(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
    );
  }
  return r.json() as Promise<ChatSessionsSaveResult>;
}
