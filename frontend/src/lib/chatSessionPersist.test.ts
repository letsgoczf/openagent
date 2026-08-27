import { describe, expect, it } from "vitest";
import { buildChatSessionsPersistBody } from "./chatSessionPersist";
import {
  CHAT_SESSIONS_VERSION,
  type ChatSessionPersisted,
} from "./chatSessionPersistence";

function session(
  id: string,
  extra?: Partial<ChatSessionPersisted>
): ChatSessionPersisted {
  return {
    id,
    title: extra?.title ?? "新会话",
    updatedAt: extra?.updatedAt ?? 1,
    messages: extra?.messages ?? [],
    lastEvidenceEntries: extra?.lastEvidenceEntries ?? [],
    lastCitations: extra?.lastCitations ?? [],
  };
}

describe("buildChatSessionsPersistBody", () => {
  const sessions = [session("s1", { title: "已有对话" }), session("s2")];

  it("skips the initial hydrate write", () => {
    expect(
      buildChatSessionsPersistBody({
        persistSkip: true,
        persistDirty: true,
        sessionsReady: true,
        activeSessionId: "s1",
        sessions,
      })
    ).toBeNull();
  });

  it("skips when no unpublished debounce is pending", () => {
    expect(
      buildChatSessionsPersistBody({
        persistSkip: false,
        persistDirty: false,
        sessionsReady: true,
        activeSessionId: "s1",
        sessions,
      })
    ).toBeNull();
  });

  it("skips before sessions have loaded", () => {
    expect(
      buildChatSessionsPersistBody({
        persistSkip: false,
        persistDirty: true,
        sessionsReady: false,
        activeSessionId: "s1",
        sessions,
      })
    ).toBeNull();
  });

  it("skips empty or mismatched snapshots", () => {
    expect(
      buildChatSessionsPersistBody({
        persistSkip: false,
        persistDirty: true,
        sessionsReady: true,
        activeSessionId: null,
        sessions,
      })
    ).toBeNull();
    expect(
      buildChatSessionsPersistBody({
        persistSkip: false,
        persistDirty: true,
        sessionsReady: true,
        activeSessionId: "s1",
        sessions: [],
      })
    ).toBeNull();
    expect(
      buildChatSessionsPersistBody({
        persistSkip: false,
        persistDirty: true,
        sessionsReady: true,
        activeSessionId: "missing",
        sessions,
      })
    ).toBeNull();
  });

  it("returns the PUT body for a pending in-memory snapshot", () => {
    const withReply = [
      session("s1", {
        title: "已有对话",
        messages: [{ id: "a1", role: "assistant", content: "刚生成的答复" }],
      }),
      session("s2"),
    ];
    expect(
      buildChatSessionsPersistBody({
        persistSkip: false,
        persistDirty: true,
        sessionsReady: true,
        activeSessionId: "s1",
        sessions: withReply,
      })
    ).toEqual({
      version: CHAT_SESSIONS_VERSION,
      activeSessionId: "s1",
      sessions: withReply,
    });
  });
});
