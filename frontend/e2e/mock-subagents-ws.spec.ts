import { test, expect } from "@playwright/test";

async function routeChatBootstrap(page: import("@playwright/test").Page) {
  await page.route("http://127.0.0.1:8000/v1/chat-sessions/state", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        json: {
          version: 1,
          activeSessionId: "s_e2e",
          sessions: [
            {
              id: "s_e2e",
              title: "新会话",
              updatedAt: Date.now(),
              messages: [],
              lastEvidenceEntries: [],
              lastCitations: [],
            },
          ],
        },
      });
      return;
    }
    await route.fulfill({ json: { ok: true } });
  });
  await page.route("http://127.0.0.1:8000/v1/agent-templates", async (route) => {
    await route.fulfill({ json: { agents: [] } });
  });
}

/**
 * 不依赖真实后端：拦截 ``ws://127.0.0.1:8000/ws``，在收到 ``chat.start`` 后回放
 * ``chat.agent_*`` 序列，用于验证子智能体侧栏与 Trace。
 */
test.describe("mock WebSocket sub-agents", () => {
  test("shows 子智能体 cards after agent_spawned sequence", async ({
    page,
  }) => {
    await routeChatBootstrap(page);
    await page.routeWebSocket("ws://127.0.0.1:8000/ws", (ws) => {
      ws.onMessage((message) => {
        let data: { type?: string; client_request_id?: string };
        try {
          data = JSON.parse(String(message)) as { type?: string };
        } catch {
          return;
        }
        if (data.type !== "chat.start") return;
        const client_request_id = data.client_request_id;

        ws.send(
          JSON.stringify({
            type: "chat.agent_spawned",
            client_request_id,
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
            client_request_id,
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
            client_request_id,
            payload: {
              agent_id: "sub_mock_1",
              output_summary: "子任务结论摘要",
            },
          })
        );
        ws.send(
          JSON.stringify({
            type: "chat.delta",
            client_request_id,
            delta_kind: "content",
            delta: "最终答复",
          })
        );
        ws.send(
          JSON.stringify({
            type: "chat.completed",
            client_request_id,
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

    // 严格模式：页面上多处 JSON trace 也包含 sub_mock_1，只断言「子智能体」区块内可见
    const agents = page.getByRole("region", { name: "子智能体" });
    await expect(agents.getByText("sub_mock_1", { exact: true })).toBeVisible();
    await expect(agents.getByText("分析子任务")).toBeVisible();
    await expect(agents.getByText("子任务结论摘要")).toBeVisible();
    await expect(page.getByText("chat.agent_spawned").first()).toBeVisible();
  });

  test("recovers controls when WebSocket closes before completion", async ({
    page,
  }) => {
    await routeChatBootstrap(page);
    await page.routeWebSocket("ws://127.0.0.1:8000/ws", (ws) => {
      ws.onMessage((message) => {
        let data: { type?: string };
        try {
          data = JSON.parse(String(message)) as { type?: string };
        } catch {
          return;
        }
        if (data.type === "chat.start") {
          void ws.close();
        }
      });
    });

    await page.goto("/chat");
    await page.getByLabel("消息").fill("任意问题");
    await page.getByRole("button", { name: "发送" }).click();

    await expect(page.getByRole("alert")).toContainText("WebSocket 连接已断开");
    await expect(page.getByLabel("消息")).toBeEnabled();
    await expect(page.getByRole("button", { name: "新建" })).toBeEnabled();
  });
});
