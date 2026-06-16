import { describe, expect, it } from "vitest";
import {
  CHAT_SESSIONS_VERSION,
  mergeChatSessionsState,
  type ChatSessionsFile,
} from "./chatSessionPersistence";

function state(
  activeSessionId: string,
  sessions: Array<{ id: string; updatedAt: number; content: string }>,
  stateRevision: number
): ChatSessionsFile {
  return {
    version: CHAT_SESSIONS_VERSION,
    activeSessionId,
    stateRevision,
    sessions: sessions.map((s) => ({
      id: s.id,
      title: s.id,
      updatedAt: s.updatedAt,
      messages: [{ id: `${s.id}_m`, role: "user", content: s.content }],
      lastEvidenceEntries: [],
      lastCitations: [],
    })),
  };
}

describe("mergeChatSessionsState", () => {
  it("preserves sessions written by different stale clients", () => {
    const remote = state("remote", [{ id: "remote", updatedAt: 10, content: "r" }], 2);
    const local = state("local", [{ id: "local", updatedAt: 11, content: "l" }], 1);

    const merged = mergeChatSessionsState(local, remote);

    expect(merged.stateRevision).toBe(2);
    expect(merged.activeSessionId).toBe("local");
    expect(merged.sessions.map((s) => s.id).sort()).toEqual(["local", "remote"]);
  });

  it("keeps the newer copy when both states contain the same session", () => {
    const remote = state("s_1", [{ id: "s_1", updatedAt: 20, content: "remote" }], 4);
    const local = state("s_1", [{ id: "s_1", updatedAt: 10, content: "local" }], 3);

    const merged = mergeChatSessionsState(local, remote);

    expect(merged.sessions).toHaveLength(1);
    expect(merged.sessions[0]!.messages[0]!.content).toBe("remote");
  });
});
