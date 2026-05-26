import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBase, wsUrl } from "./api";
import { putChatSessionsState } from "./chatSessionsApi";

afterEach(() => {
  vi.restoreAllMocks();
  delete process.env.NEXT_PUBLIC_API_BASE;
});

describe("api", () => {
  it("wsUrl uses ws for http origin", () => {
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
    expect(wsUrl()).toBe("ws://127.0.0.1:8000/ws");
  });
});

describe("chatSessionsApi", () => {
  it("sends baseRevision and omits response-only stateRevision", async () => {
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, stateRevision: 8 }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );

    const result = await putChatSessionsState(
      {
        version: 1,
        activeSessionId: "s_1",
        sessions: [],
        stateRevision: 7,
      },
      7
    );

    expect(result.stateRevision).toBe(8);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/v1/chat-sessions/state",
      expect.objectContaining({
        method: "PUT",
        headers: { "Content-Type": "application/json" },
      })
    );
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({
      version: 1,
      activeSessionId: "s_1",
      sessions: [],
      baseRevision: 7,
    });
  });
});
