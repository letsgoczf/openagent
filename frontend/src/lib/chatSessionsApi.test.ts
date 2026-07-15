import { afterEach, describe, expect, it, vi } from "vitest";
import type {
  ChatSessionPersisted,
  ChatSessionsFile,
} from "./chatSessionPersistence";
import {
  mergeChatSessionLists,
  putChatSessionsStateWithMerge,
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

describe("chat sessions concurrency", () => {
  it("keeps sessions created by both snapshots", () => {
    const merged = mergeChatSessionLists(
      [session("local", 2)],
      [session("remote", 1)]
    );

    expect(merged.map((item) => item.id)).toEqual(["local", "remote"]);
  });

  it("reloads, merges and retries after a stale write", async () => {
    const local: ChatSessionsFile = {
      version: 1,
      activeSessionId: "local",
      sessions: [session("local", 2)],
    };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response("", { status: 409 }))
      .mockResolvedValueOnce(
        Response.json({
          version: 1,
          activeSessionId: "remote",
          sessions: [session("remote", 1)],
          stateRevision: 1,
        })
      )
      .mockResolvedValueOnce(
        Response.json({ ok: true, stateRevision: 2 })
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await putChatSessionsStateWithMerge(local, 0);

    expect(result.conflictMerged).toBe(true);
    expect(result.state.stateRevision).toBe(2);
    expect(result.state.sessions.map((item) => item.id)).toEqual([
      "local",
      "remote",
    ]);
    const retryRequest = fetchMock.mock.calls[2]![1] as RequestInit;
    expect(JSON.parse(String(retryRequest.body))).toMatchObject({
      baseRevision: 1,
      sessions: [{ id: "local" }, { id: "remote" }],
    });
  });
});
