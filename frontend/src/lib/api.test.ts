import { describe, expect, it } from "vitest";
import { apiBase, wsUrl } from "./api";
import { clearChatSessionMemory } from "./chatSessionsApi";

describe("api", () => {
  it("wsUrl uses ws for http origin", () => {
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
    expect(wsUrl()).toBe("ws://127.0.0.1:8000/ws");
  });

  it("clearChatSessionMemory calls encoded session memory endpoint", async () => {
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
    const prevFetch = globalThis.fetch;
    const calls: Array<[RequestInfo | URL, RequestInit | undefined]> = [];
    globalThis.fetch = (async (input, init) => {
      calls.push([input, init]);
      return new Response("{}", { status: 200 });
    }) as typeof fetch;
    try {
      await clearChatSessionMemory("s/with space");
    } finally {
      globalThis.fetch = prevFetch;
    }
    expect(String(calls[0]![0])).toBe(
      "http://127.0.0.1:8000/v1/chat-sessions/s%2Fwith%20space/memory"
    );
    expect(calls[0]![1]?.method).toBe("DELETE");
  });
});
