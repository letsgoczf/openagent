import { describe, expect, it } from "vitest";
import { isSafeChatSessionsPersist } from "./chatSessionPersistGuard";

const sessions = [{ id: "s1" }, { id: "s2" }];

describe("isSafeChatSessionsPersist", () => {
  const ok = {
    hydrateSucceeded: true,
    hydratedApiBase: "http://127.0.0.1:8000",
    currentApiBase: "http://127.0.0.1:8000",
    sessionsReady: true,
    activeSessionId: "s1",
    sessions,
  };

  it("allows persist after a successful hydrate from the same API", () => {
    expect(isSafeChatSessionsPersist(ok)).toBe(true);
  });

  it("blocks persist when the initial GET failed (local empty fallback)", () => {
    expect(
      isSafeChatSessionsPersist({
        ...ok,
        hydrateSucceeded: false,
        hydratedApiBase: null,
        sessions: [{ id: "local-empty" }],
        activeSessionId: "local-empty",
      })
    ).toBe(false);
  });

  it("blocks persist when API base changed since hydrate", () => {
    expect(
      isSafeChatSessionsPersist({
        ...ok,
        currentApiBase: "http://127.0.0.1:9000",
      })
    ).toBe(false);
  });

  it("blocks persist before sessions are ready or when the snapshot is empty", () => {
    expect(isSafeChatSessionsPersist({ ...ok, sessionsReady: false })).toBe(
      false
    );
    expect(isSafeChatSessionsPersist({ ...ok, activeSessionId: null })).toBe(
      false
    );
    expect(isSafeChatSessionsPersist({ ...ok, sessions: [] })).toBe(false);
    expect(
      isSafeChatSessionsPersist({ ...ok, activeSessionId: "missing" })
    ).toBe(false);
  });
});
