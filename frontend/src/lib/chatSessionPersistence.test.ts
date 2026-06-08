import { describe, expect, it } from "vitest";
import {
  CHAT_SESSIONS_VERSION,
  mergeChatSessionsFile,
  type ChatSessionsFile,
} from "./chatSessionPersistence";

function state(
  activeSessionId: string,
  sessions: Array<{ id: string; updatedAt: number; content: string }>
): ChatSessionsFile {
  return {
    version: CHAT_SESSIONS_VERSION,
    activeSessionId,
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

describe("mergeChatSessionsFile", () => {
  it("preserves legacy sessions missing from a non-empty remote state", () => {
    const remote = state("remote", [
      { id: "remote", updatedAt: 10, content: "remote only" },
    ]);
    const legacy = state("legacy", [
      { id: "legacy", updatedAt: 20, content: "legacy only" },
    ]);

    const merged = mergeChatSessionsFile(remote, legacy);

    expect(merged.changed).toBe(true);
    expect(merged.state.sessions.map((s) => s.id)).toEqual(["legacy", "remote"]);
    expect(merged.state.activeSessionId).toBe("remote");
  });

  it("keeps the newer legacy copy for duplicate session ids", () => {
    const remote = state("s1", [{ id: "s1", updatedAt: 10, content: "old" }]);
    const legacy = state("s1", [{ id: "s1", updatedAt: 30, content: "new" }]);

    const merged = mergeChatSessionsFile(remote, legacy);

    expect(merged.changed).toBe(true);
    expect(merged.state.sessions).toHaveLength(1);
    expect(merged.state.sessions[0]!.messages[0]!.content).toBe("new");
  });
});
