import { apiBase } from "@/lib/api";
import type {
  ChatSessionPersisted,
  ChatSessionsFile,
  ChatSessionsState,
} from "@/lib/chatSessionPersistence";

export class ChatSessionsConflictError extends Error {
  constructor() {
    super("会话已在其他窗口中更新");
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
  body: ChatSessionsFile,
  baseRevision: number
): Promise<number> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, baseRevision }),
  });
  if (r.status === 409) {
    throw new ChatSessionsConflictError();
  }
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
    );
  }
  const result = (await r.json()) as { stateRevision: number };
  return result.stateRevision;
}

export function mergeChatSessionSnapshots(
  remote: ChatSessionPersisted[],
  local: ChatSessionPersisted[]
): ChatSessionPersisted[] {
  const merged = new Map(remote.map((session) => [session.id, session]));
  for (const session of local) {
    const existing = merged.get(session.id);
    if (!existing) {
      merged.set(session.id, session);
      continue;
    }
    const newest = session.updatedAt >= existing.updatedAt ? session : existing;
    const older = newest === session ? existing : session;
    const messageIds = new Set(newest.messages.map((message) => message.id));
    const messages = [
      ...newest.messages,
      ...older.messages.filter((message) => !messageIds.has(message.id)),
    ];
    merged.set(session.id, { ...newest, messages });
  }
  return [...merged.values()];
}

export async function persistChatSessionsState(
  initial: ChatSessionsFile,
  initialRevision: number
): Promise<ChatSessionsState> {
  let desired = initial;
  let baseRevision = initialRevision;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const stateRevision = await putChatSessionsState(desired, baseRevision);
      return { ...desired, stateRevision };
    } catch (error) {
      if (!(error instanceof ChatSessionsConflictError) || attempt === 2) {
        throw error;
      }
      const remote = await fetchChatSessionsState();
      const sessions = mergeChatSessionSnapshots(
        remote.sessions,
        desired.sessions
      );
      const activeSessionId = sessions.some(
        (session) => session.id === desired.activeSessionId
      )
        ? desired.activeSessionId
        : remote.activeSessionId;
      desired = { ...desired, activeSessionId, sessions };
      baseRevision = remote.stateRevision;
    }
  }

  throw new Error("保存会话失败");
}
