import { describe, expect, it } from "vitest";
import {
  CHAT_SESSIONS_VERSION,
  mergeLegacyChatSessions,
  type ChatSessionsFile,
} from "./chatSessionPersistence";

const baseState = (
  activeSessionId: string,
  sessions: ChatSessionsFile["sessions"]
): ChatSessionsFile => ({
  version: CHAT_SESSIONS_VERSION,
  activeSessionId,
  sessions,
});

const session = (
  id: string,
  updatedAt: number,
  messages: ChatSessionsFile["sessions"][number]["messages"] = [],
  title = "新会话"
): ChatSessionsFile["sessions"][number] => ({
  id,
  title,
  updatedAt,
  messages,
  lastEvidenceEntries: [],
  lastCitations: [],
});

describe("mergeLegacyChatSessions", () => {
  it("preserves legacy history when the server already has a placeholder session", () => {
    const remote = baseState("server-empty", [session("server-empty", 20)]);
    const legacy = baseState("legacy-history", [
      session("legacy-history", 10, [
        { id: "m1", role: "user", content: "important old question" },
      ]),
    ]);

    const result = mergeLegacyChatSessions(remote, legacy);

    expect(result.changed).toBe(true);
    expect(result.state.activeSessionId).toBe("legacy-history");
    expect(result.state.sessions.map((s) => s.id)).toEqual([
      "server-empty",
      "legacy-history",
    ]);
  });

  it("replaces an empty duplicate server session with legacy content", () => {
    const remote = baseState("same", [session("same", 20)]);
    const legacy = baseState("same", [
      session("same", 10, [
        { id: "m2", role: "assistant", content: "old answer" },
      ]),
    ]);

    const result = mergeLegacyChatSessions(remote, legacy);

    expect(result.changed).toBe(true);
    expect(result.state.sessions).toHaveLength(1);
    expect(result.state.sessions[0]!.messages).toEqual([
      { id: "m2", role: "assistant", content: "old answer" },
    ]);
  });

  it("does not import an empty legacy placeholder over real server state", () => {
    const remote = baseState("remote-history", [
      session("remote-history", 20, [
        { id: "m3", role: "user", content: "new" },
      ]),
    ]);
    const legacy = baseState("legacy-empty", [session("legacy-empty", 10)]);

    const result = mergeLegacyChatSessions(remote, legacy);

    expect(result.changed).toBe(false);
    expect(result.state).toEqual(remote);
  });
});
