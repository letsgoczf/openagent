import { apiBase, SETTINGS_CHANGE_EVENT } from "@/lib/api";

export type AgentTemplateItem = { id: string; blurb: string };

export type AgentTemplatesResponse = { agents: AgentTemplateItem[] };

export async function fetchAgentTemplates(): Promise<AgentTemplateItem[]> {
  const r = await fetch(`${apiBase()}/v1/agent-templates`);
  if (!r.ok) {
    throw new Error(`加载 Agent 列表失败: HTTP ${r.status}`);
  }
  const data = (await r.json()) as AgentTemplatesResponse;
  return Array.isArray(data.agents) ? data.agents : [];
}

/** 在浏览器中监听 API 基址变更后重新拉取。 */
export function subscribeAgentTemplatesReload(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const fn = () => cb();
  window.addEventListener(SETTINGS_CHANGE_EVENT, fn);
  return () => window.removeEventListener(SETTINGS_CHANGE_EVENT, fn);
}
