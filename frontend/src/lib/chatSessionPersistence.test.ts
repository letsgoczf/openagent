import { describe, expect, it } from "vitest";
import {
  CHAT_SESSIONS_VERSION,
  mergeChatSessionsState,
  type ChatSessionPersisted,
  type ChatSessionsFile,
} from "./chatSessionPersistence";

function session(id: string, updatedAt: number): ChatSessionPersisted {
  return {
    id,
    title: id,
    updatedAt,
    messages: [],
    lastEvidenceEntries: [],
    lastCitations: [],
  };
}

function state(
  sessions: ChatSessionPersisted[],
  activeSessionId: string | null,
  stateRevision: number
): ChatSessionsFile {
  return {
    version: CHAT_SESSIONS_VERSION,
    activeSessionId,
    sessions,
    stateRevision,
  };
}

describe("mergeChatSessionsState", () => {
  it("preserves legacy sessions when remote state is already non-empty", () => {
    const remote = state([session("remote", 10)], "remote", 7);
    const legacy = state([session("legacy", 20)], "legacy", 0);

    const merged = mergeChatSessionsState(remote, legacy, legacy.activeSessionId);

    expect(merged.stateRevision).toBe(7);
    expect(merged.activeSessionId).toBe("legacy");
    expect(merged.sessions.map((s) => s.id)).toEqual(["legacy", "remote"]);
  });

  it("keeps newer local session payload on id conflicts", () => {
    const remoteSession = { ...session("same", 10), title: "remote" };
    const localSession = { ...session("same", 20), title: "local" };

    const merged = mergeChatSessionsState(
      state([remoteSession], "same", 3),
      state([localSession], "same", 0),
      "same"
    );

    expect(merged.sessions).toHaveLength(1);
    expect(merged.sessions[0]!.title).toBe("local");
  });
});
