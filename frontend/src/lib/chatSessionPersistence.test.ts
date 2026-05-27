import { describe, expect, it } from "vitest";
import {
  CHAT_SESSIONS_VERSION,
  mergeChatSessionFiles,
  type ChatSessionsFile,
} from "./chatSessionPersistence";

function file(activeSessionId: string, sessions: ChatSessionsFile["sessions"]) {
  return {
    version: CHAT_SESSIONS_VERSION,
    activeSessionId,
    sessions,
  };
}

describe("chat session persistence", () => {
  it("keeps legacy history when the server only has an empty placeholder", () => {
    const remote = file("remote-empty", [
      {
        id: "remote-empty",
        title: "新会话",
        updatedAt: 200,
        messages: [],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);
    const legacy = file("legacy-chat", [
      {
        id: "legacy-chat",
        title: "Important history",
        updatedAt: 100,
        messages: [{ id: "m1", role: "user", content: "do not lose this" }],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);

    const merged = mergeChatSessionFiles(remote, legacy);

    expect(merged.changed).toBe(true);
    expect(merged.file.activeSessionId).toBe("legacy-chat");
    expect(merged.file.sessions.map((s) => s.id)).toEqual([
      "remote-empty",
      "legacy-chat",
    ]);
    expect(
      merged.file.sessions.find((s) => s.id === "legacy-chat")?.messages[0]
        ?.content
    ).toBe("do not lose this");
  });

  it("prefers a legacy copy over a same-id remote placeholder", () => {
    const remote = file("same", [
      {
        id: "same",
        title: "新会话",
        updatedAt: 300,
        messages: [],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);
    const legacy = file("same", [
      {
        id: "same",
        title: "Recovered",
        updatedAt: 100,
        messages: [{ id: "m1", role: "assistant", content: "saved answer" }],
        lastEvidenceEntries: [],
        lastCitations: [],
      },
    ]);

    const merged = mergeChatSessionFiles(remote, legacy);

    expect(merged.changed).toBe(true);
    expect(merged.file.sessions).toHaveLength(1);
    expect(merged.file.sessions[0]?.title).toBe("Recovered");
    expect(merged.file.sessions[0]?.messages[0]?.content).toBe("saved answer");
  });
});
