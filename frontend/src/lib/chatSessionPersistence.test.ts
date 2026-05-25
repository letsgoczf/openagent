import { describe, expect, it } from "vitest";
import {
  CHAT_SESSIONS_VERSION,
  chatSessionsFileEquals,
  mergeChatSessionsFiles,
  type ChatSessionsFile,
} from "./chatSessionPersistence";

function snapshot(
  activeSessionId: string,
  sessions: Array<{ id: string; updatedAt: number; title?: string }>,
  revision?: number
): ChatSessionsFile {
  return {
    version: CHAT_SESSIONS_VERSION,
    activeSessionId,
    revision,
    sessions: sessions.map((s) => ({
      id: s.id,
      title: s.title ?? s.id,
      updatedAt: s.updatedAt,
      messages: [{ id: `${s.id}_m`, role: "user", content: s.id }],
      lastEvidenceEntries: [],
      lastCitations: [],
    })),
  };
}

describe("mergeChatSessionsFiles", () => {
  it("keeps remote data when it is newer for the same session", () => {
    const remote = snapshot("s1", [{ id: "s1", updatedAt: 20 }], 3);
    const local = snapshot("s1", [{ id: "s1", updatedAt: 10 }]);

    const merged = mergeChatSessionsFiles(remote, local);

    expect(merged.revision).toBe(3);
    expect(merged.sessions).toHaveLength(1);
    expect(merged.sessions[0]?.updatedAt).toBe(20);
    expect(merged.activeSessionId).toBe("s1");
    expect(chatSessionsFileEquals(merged, remote)).toBe(true);
  });

  it("preserves local-only sessions after a failed remote save", () => {
    const remote = snapshot("s1", [{ id: "s1", updatedAt: 10 }], 4);
    const local = snapshot(
      "s2",
      [
        { id: "s1", updatedAt: 10 },
        { id: "s2", updatedAt: 30 },
      ],
    );

    const merged = mergeChatSessionsFiles(remote, local);

    expect(merged.sessions.map((s) => s.id)).toEqual(["s2", "s1"]);
    expect(merged.activeSessionId).toBe("s2");
    expect(chatSessionsFileEquals(merged, remote)).toBe(false);
  });
});
