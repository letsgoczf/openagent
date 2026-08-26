import { describe, expect, it } from "vitest";
import { claimSendQuerySlot, releaseSendQuerySlot } from "./sendQueryGuard";

describe("claimSendQuerySlot", () => {
  it("accepts the first claim and rejects a synchronous second claim", () => {
    const inFlight = { current: false };
    expect(claimSendQuerySlot(inFlight)).toBe(true);
    expect(inFlight.current).toBe(true);
    expect(claimSendQuerySlot(inFlight)).toBe(false);
    expect(inFlight.current).toBe(true);
  });

  it("allows another send after the slot is released", () => {
    const inFlight = { current: false };
    expect(claimSendQuerySlot(inFlight)).toBe(true);
    releaseSendQuerySlot(inFlight);
    expect(inFlight.current).toBe(false);
    expect(claimSendQuerySlot(inFlight)).toBe(true);
  });
});
