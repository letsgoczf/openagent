import { describe, expect, it } from "vitest";
import {
  CHAT_SESSIONS_VERSION,
  mergeChatSessionsState,
  type ChatSessionsFile,
} from "./chatSessionPersistence";

function state(
  activeSessionId: string | null,
  sessions: ChatSessionsFile["sessions"]
): ChatSessionsFile {
  return {
    version: CHAT_SESSIONS_VERSION,
    activeSessionId,
    sessions,
  };
}

describe("mergeChatSessionsState", () => {
  it("keeps legacy sessions when remote already has a session", () => {
    const remote = state("remote_empty", [
      {
        id: "remote_empty",
        title: "新会话",
        updatedAt: 1,
        messages: [],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);
    const legacy = state("legacy_chat", [
      {
        id: "legacy_chat",
        title: "important",
        updatedAt: 2,
        messages: [{ id: "m1", role: "user", content: "keep me" }],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);

    const merged = mergeChatSessionsState(remote, legacy);

    expect(merged.sessions.map((s) => s.id).sort()).toEqual([
      "legacy_chat",
      "remote_empty",
    ]);
    expect(merged.activeSessionId).toBe("legacy_chat");
  });

  it("uses the richer duplicate session", () => {
    const remote = state("s1", [
      {
        id: "s1",
        title: "old",
        updatedAt: 1,
        messages: [],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);
    const local = state("s1", [
      {
        id: "s1",
        title: "new",
        updatedAt: 2,
        messages: [{ id: "m1", role: "assistant", content: "answer" }],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);

    const merged = mergeChatSessionsState(remote, local);

    expect(merged.sessions).toHaveLength(1);
    expect(merged.sessions[0]!.title).toBe("new");
    expect(merged.sessions[0]!.messages[0]!.content).toBe("answer");
  });
});
