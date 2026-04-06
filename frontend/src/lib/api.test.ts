import { describe, expect, it } from "vitest";
import { apiBase, wsUrl } from "./api";

describe("api", () => {
  it("wsUrl uses ws for http origin", () => {
    process.env.NEXT_PUBLIC_API_BASE = "http://127.0.0.1:8000";
    expect(wsUrl()).toBe("ws://127.0.0.1:8000/ws");
  });
});
