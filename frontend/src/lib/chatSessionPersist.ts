import {
  CHAT_SESSIONS_VERSION,
  type ChatSessionPersisted,
  type ChatSessionsFile,
} from "@/lib/chatSessionPersistence";

/**
 * 防抖写入在组件卸载 / pagehide 时会被 clearTimeout 丢掉。
 * 仅当 hydrate 之后确有未落盘的脏快照时返回 PUT body。
 */
export function buildChatSessionsPersistBody(input: {
  persistSkip: boolean;
  persistDirty: boolean;
  sessionsReady: boolean;
  activeSessionId: string | null;
  sessions: ChatSessionPersisted[];
}): ChatSessionsFile | null {
  if (input.persistSkip || !input.persistDirty || !input.sessionsReady) {
    return null;
  }
  const activeSessionId = input.activeSessionId;
  if (!activeSessionId || input.sessions.length === 0) return null;
  if (!input.sessions.some((s) => s.id === activeSessionId)) return null;
  return {
    version: CHAT_SESSIONS_VERSION,
    activeSessionId,
    sessions: input.sessions,
  };
}
