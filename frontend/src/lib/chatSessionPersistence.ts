import type {
  ChatMessage,
  CitationDTO,
  EvidenceEntryDTO,
} from "@/types/chat";

export const CHAT_SESSIONS_STORAGE_KEY = "openagent.chat.sessions.v1";

export const CHAT_SESSIONS_VERSION = 1;

export interface ChatSessionPersisted {
  id: string;
  title: string;
  updatedAt: number;
  messages: ChatMessage[];
  lastEvidenceEntries: EvidenceEntryDTO[];
  lastCitations: CitationDTO[];
}

export interface ChatSessionsFile {
  version: number;
  activeSessionId: string;
  sessions: ChatSessionPersisted[];
}

function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `s_${crypto.randomUUID()}`;
  }
  return `s_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export function createEmptySession(): ChatSessionPersisted {
  return {
    id: newSessionId(),
    title: "新会话",
    updatedAt: Date.now(),
    messages: [],
    lastEvidenceEntries: [],
    lastCitations: [],
  };
}

export function loadChatSessionsFile(): ChatSessionsFile | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CHAT_SESSIONS_STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as unknown;
    if (!data || typeof data !== "object") return null;
    const obj = data as Record<string, unknown>;
    if (obj.version !== CHAT_SESSIONS_VERSION) return null;
    const activeSessionId =
      typeof obj.activeSessionId === "string" ? obj.activeSessionId : "";
    const sessions = obj.sessions;
    if (!Array.isArray(sessions) || sessions.length === 0) return null;
    const cleaned: ChatSessionPersisted[] = [];
    for (const s of sessions) {
      if (!s || typeof s !== "object") continue;
      const row = s as Record<string, unknown>;
      const id = typeof row.id === "string" ? row.id : "";
      if (!id) continue;
      cleaned.push({
        id,
        title: typeof row.title === "string" ? row.title : "新会话",
        updatedAt:
          typeof row.updatedAt === "number" ? row.updatedAt : Date.now(),
        messages: Array.isArray(row.messages) ? (row.messages as ChatMessage[]) : [],
        lastEvidenceEntries: Array.isArray(row.lastEvidenceEntries)
          ? (row.lastEvidenceEntries as EvidenceEntryDTO[])
          : [],
        lastCitations: Array.isArray(row.lastCitations)
          ? (row.lastCitations as CitationDTO[])
          : [],
      });
    }
    if (!cleaned.length) return null;
    const activeOk = cleaned.some((x) => x.id === activeSessionId);
    return {
      version: CHAT_SESSIONS_VERSION,
      activeSessionId: activeOk ? activeSessionId : cleaned[0]!.id,
      sessions: cleaned,
    };
  } catch {
    return null;
  }
}

export function saveChatSessionsFile(data: ChatSessionsFile): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      CHAT_SESSIONS_STORAGE_KEY,
      JSON.stringify(data)
    );
  } catch {
    /* quota or private mode */
  }
}

/** 迁移到服务端 DB 后清除旧版 localStorage，避免两套数据源混淆 */
export function clearLegacyChatSessionsStorage(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CHAT_SESSIONS_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
