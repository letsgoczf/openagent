import { describe, expect, it } from "vitest";
import type { ChatSessionPersisted } from "./chatSessionPersistence";
import {
  CHAT_SESSIONS_VERSION,
  hasMeaningfulChatSession,
  mergeChatSessionsState,
} from "./chatSessionPersistence";

function session(
  id: string,
  updatedAt: number,
  content = "",
  title = "新会话"
): ChatSessionPersisted {
  return {
    id,
    title,
    updatedAt,
    messages: content ? [{ id: `m_${id}`, role: "user", content }] : [],
    lastEvidenceEntries: [],
    lastCitations: [],
  };
}

describe("hasMeaningfulChatSession", () => {
  it("ignores empty default sessions", () => {
    expect(hasMeaningfulChatSession(session("s_empty", 1))).toBe(false);
  });

  it("keeps sessions with messages or custom titles", () => {
    expect(hasMeaningfulChatSession(session("s_msg", 1, "hello"))).toBe(true);
    expect(hasMeaningfulChatSession(session("s_title", 1, "", "saved"))).toBe(
      true
    );
  });
});

describe("mergeChatSessionsState", () => {
  it("preserves remote sessions when merging legacy local state", () => {
    const merged = mergeChatSessionsState(
      {
        version: CHAT_SESSIONS_VERSION,
        activeSessionId: "s_remote",
        sessions: [session("s_remote", 10, "remote")],
      },
      {
        version: CHAT_SESSIONS_VERSION,
        activeSessionId: "s_legacy",
        sessions: [session("s_legacy", 20, "legacy")],
      }
    );

    expect(merged.sessions.map((s) => s.id)).toEqual(["s_legacy", "s_remote"]);
    expect(merged.activeSessionId).toBe("s_legacy");
  });

  it("uses the newest session payload for duplicate ids", () => {
    const merged = mergeChatSessionsState(
      {
        version: CHAT_SESSIONS_VERSION,
        activeSessionId: "s_same",
        sessions: [session("s_same", 10, "old")],
      },
      {
        version: CHAT_SESSIONS_VERSION,
        activeSessionId: "s_same",
        sessions: [session("s_same", 20, "new")],
      }
    );

    expect(merged.sessions).toHaveLength(1);
    expect(merged.sessions[0]!.messages[0]!.content).toBe("new");
  });
});
