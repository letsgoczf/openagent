import { apiBase } from "@/lib/api";
import type { ChatSessionsFile } from "@/lib/chatSessionPersistence";

export class ChatSessionsApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;

  constructor(
    message: string,
    options: {
      status: number;
      code?: string;
      detail?: unknown;
    }
  ) {
    super(message);
    this.name = "ChatSessionsApiError";
    this.status = options.status;
    this.code = options.code;
    this.detail = options.detail;
  }
}

async function chatSessionsError(r: Response, fallback: string): Promise<ChatSessionsApiError> {
  const text = await r.text().catch(() => "");
  let code: string | undefined;
  let message = fallback;
  let detail: unknown;
  if (text) {
    try {
      const parsed = JSON.parse(text) as {
        error?: { code?: string; message?: string; detail?: unknown };
      };
      code = parsed.error?.code;
      message = parsed.error?.message ?? message;
      detail = parsed.error?.detail;
    } catch {
      message = `${fallback}: ${text.slice(0, 200)}`;
    }
  }
  return new ChatSessionsApiError(message, {
    status: r.status,
    code,
    detail,
  });
}

export async function fetchChatSessionsState(): Promise<ChatSessionsFile> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`);
  if (!r.ok) {
    throw await chatSessionsError(r, `加载会话失败: HTTP ${r.status}`);
  }
  return r.json() as Promise<ChatSessionsFile>;
}

export async function putChatSessionsState(
  body: ChatSessionsFile
): Promise<number> {
  const r = await fetch(`${apiBase()}/v1/chat-sessions/state`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    throw await chatSessionsError(r, `保存会话失败: HTTP ${r.status}`);
  }
  const data = (await r.json()) as { stateRevision?: number };
  return typeof data.stateRevision === "number"
    ? data.stateRevision
    : (body.baseRevision ?? 0) + 1;
}
