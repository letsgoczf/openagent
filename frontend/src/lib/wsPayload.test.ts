import { describe, expect, it } from "vitest";
import { readWsPayload, subAgentTaskSummary } from "./wsPayload";

describe("readWsPayload", () => {
  it("returns empty object when payload missing", () => {
    expect(readWsPayload({ type: "x" })).toEqual({});
  });

  it("returns payload object", () => {
    expect(
      readWsPayload({ type: "chat.agent_spawned", payload: { agent_id: "a1" } })
    ).toEqual({ agent_id: "a1" });
  });
});

describe("subAgentTaskSummary", () => {
  it("picks first known field", () => {
    expect(subAgentTaskSummary({ task_summary: "  T  " })).toBe("T");
    expect(subAgentTaskSummary({ subtask: "S" })).toBe("S");
    expect(subAgentTaskSummary({})).toBeUndefined();
  });
});
