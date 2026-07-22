import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  ChatSessionPersisted,
  ChatSessionsFile,
} from "./chatSessionPersistence";
import {
  mergeChatSessionSnapshots,
  persistChatSessionsState,
} from "./chatSessionsApi";

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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("chat session conflict handling", () => {
  it("merges sessions and keeps the newest copy of matching ids", () => {
    const remoteShared = session("shared", 2);
    remoteShared.messages = [{ id: "remote-message", role: "user", content: "r" }];
    const localShared = session("shared", 5);
    localShared.messages = [{ id: "local-message", role: "user", content: "l" }];
    const merged = mergeChatSessionSnapshots(
      [session("remote", 3), remoteShared],
      [session("local", 4), localShared]
    );

    expect(new Set(merged.map((item) => item.id))).toEqual(
      new Set(["remote", "local", "shared"])
    );
    const shared = merged.find((item) => item.id === "shared");
    expect(shared?.updatedAt).toBe(5);
    expect(new Set(shared?.messages.map((message) => message.id))).toEqual(
      new Set(["remote-message", "local-message"])
    );
  });

  it("refetches, merges, and retries after a stale write", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("", { status: 409 }))
      .mockResolvedValueOnce(
        Response.json({
          version: 1,
          stateRevision: 5,
          activeSessionId: "remote",
          sessions: [session("remote", 5)],
        })
      )
      .mockResolvedValueOnce(
        Response.json({ ok: true, stateRevision: 6 })
      );
    vi.stubGlobal("fetch", fetchMock);

    const local: ChatSessionsFile = {
      version: 1,
      activeSessionId: "local",
      sessions: [session("local", 4)],
    };
    const persisted = await persistChatSessionsState(local, 4);

    expect(persisted.stateRevision).toBe(6);
    expect(new Set(persisted.sessions.map((item) => item.id))).toEqual(
      new Set(["remote", "local"])
    );
    const retryBody = JSON.parse(
      (fetchMock.mock.calls[2]?.[1] as RequestInit).body as string
    ) as { baseRevision: number; sessions: ChatSessionPersisted[] };
    expect(retryBody.baseRevision).toBe(5);
    expect(new Set(retryBody.sessions.map((item) => item.id))).toEqual(
      new Set(["remote", "local"])
    );
  });
});
