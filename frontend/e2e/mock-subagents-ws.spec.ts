import { test, expect } from "@playwright/test";

/**
 * 不依赖真实后端：拦截 ``ws://127.0.0.1:8000/ws``，在收到 ``chat.start`` 后回放
 * ``chat.agent_*`` 序列，用于验证子智能体侧栏与 Trace。
 */
test.describe("mock WebSocket sub-agents", () => {
  test("shows 子智能体 cards after agent_spawned sequence", async ({
    page,
  }) => {
    await page.routeWebSocket("ws://127.0.0.1:8000/ws", (ws) => {
      ws.onMessage((message) => {
        let data: { type?: string };
        try {
          data = JSON.parse(String(message)) as { type?: string };
        } catch {
          return;
        }
        if (data.type !== "chat.start") return;

        ws.send(
          JSON.stringify({
            type: "chat.agent_spawned",
            payload: {
              agent_id: "sub_mock_1",
              profile_id: "analyst",
              task_summary: "分析子任务",
            },
          })
        );
        ws.send(
          JSON.stringify({
            type: "chat.agent_progress",
            payload: {
              agent_id: "sub_mock_1",
              step: 2,
              detail: "检索文档",
            },
          })
        );
        ws.send(
          JSON.stringify({
            type: "chat.agent_completed",
            payload: {
              agent_id: "sub_mock_1",
              output_summary: "子任务结论摘要",
            },
          })
        );
        ws.send(
          JSON.stringify({
            type: "chat.delta",
            delta_kind: "content",
            delta: "最终答复",
          })
        );
        ws.send(
          JSON.stringify({
            type: "chat.completed",
            answer: "",
            citations: [],
            evidence_entries: [],
          })
        );
      });
    });

    await page.goto("/chat");
    await page.getByLabel("消息").fill("任意问题");
    await page.getByRole("button", { name: "发送" }).click();

    await expect(page.getByText("sub_mock_1")).toBeVisible();
    await expect(page.getByText("分析子任务")).toBeVisible();
    await expect(page.getByText("子任务结论摘要")).toBeVisible();
    await expect(page.getByText("chat.agent_spawned")).toBeVisible();
  });
});
