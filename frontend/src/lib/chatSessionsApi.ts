import { apiBase } from "@/lib/api";
import {
  CHAT_SESSIONS_VERSION,
  type ChatSessionPersisted,
  type ChatSessionsFile,
  type ChatSessionsState,
} from "@/lib/chatSessionPersistence";

export class ChatSessionsConflictError extends Error {
  constructor() {
    super("聊天会话已在其他页面更新");
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
  const response = (await r.json()) as { stateRevision?: unknown };
  if (
    typeof response.stateRevision !== "number" ||
    !Number.isInteger(response.stateRevision) ||
    response.stateRevision < 0
  ) {
    throw new Error("保存会话失败: 服务端未返回有效修订号");
  }
  return response.stateRevision;
}

export function mergeChatSessionLists(
  local: ChatSessionPersisted[],
  remote: ChatSessionPersisted[]
): ChatSessionPersisted[] {
  const merged = new Map(remote.map((session) => [session.id, session]));
  for (const session of local) {
    const current = merged.get(session.id);
    if (!current || session.updatedAt >= current.updatedAt) {
      merged.set(session.id, session);
    }
  }
  return [...merged.values()].sort((a, b) => b.updatedAt - a.updatedAt);
}

export interface SaveChatSessionsResult {
  state: ChatSessionsState;
  conflictMerged: boolean;
}

export async function putChatSessionsStateWithMerge(
  body: ChatSessionsFile,
  baseRevision: number
): Promise<SaveChatSessionsResult> {
  let desired = body;
  let revision = baseRevision;
  let conflictMerged = false;

  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      const stateRevision = await putChatSessionsState(desired, revision);
      return {
        state: { ...desired, stateRevision },
        conflictMerged,
      };
    } catch (error) {
      if (!(error instanceof ChatSessionsConflictError)) throw error;

      conflictMerged = true;
      const remote = await fetchChatSessionsState();
      const sessions = mergeChatSessionLists(desired.sessions, remote.sessions);
      const activeSessionId = sessions.some(
        (session) => session.id === desired.activeSessionId
      )
        ? desired.activeSessionId
        : remote.activeSessionId && sessions.some(
              (session) => session.id === remote.activeSessionId
            )
          ? remote.activeSessionId
          : sessions[0]!.id;
      desired = {
        version: CHAT_SESSIONS_VERSION,
        activeSessionId,
        sessions,
      };
      revision = remote.stateRevision;
    }
  }

  throw new Error("保存会话失败: 会话状态持续发生并发更新");
}
