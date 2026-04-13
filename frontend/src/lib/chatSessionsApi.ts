import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export async function fetchChatSessionsState(): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw new Error(`加载会话失败: HTTP ${r.status}`);
  }
  return r.json() as Promise<ChatSessionsFile>;
}

export async function putChatSessionsState(body: ChatSessionsFile): Promise<void> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(
      `保存会话失败: HTTP ${r.status}${t ? ` ${t.slice(0, 200)}` : ""}`
    );
  }
}
