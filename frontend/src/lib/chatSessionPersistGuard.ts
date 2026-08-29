import type { ChatSessionPersisted } from "@/lib/chatSessionPersistence";

/**
 * PUT /v1/chat-sessions/state 会 DELETE 整张 ui_chat_session 再插入当前快照。
 * 因此只有「已从当前 API 成功 hydrate」的快照才允许写回。
 */
export function isSafeChatSessionsPersist(input: {
  hydrateSucceeded: boolean;
  hydratedApiBase: string | null;
  currentApiBase: string;
  sessionsReady: boolean;
  activeSessionId: string | null;
  sessions: Pick<ChatSessionPersisted, "id">[];
}): boolean {
  if (!input.hydrateSucceeded) return false;
  if (!input.hydratedApiBase) return false;
  if (input.hydratedApiBase !== input.currentApiBase) return false;
  if (!input.sessionsReady) return false;
  if (!input.activeSessionId || input.sessions.length === 0) return false;
  return input.sessions.some((s) => s.id === input.activeSessionId);
}
