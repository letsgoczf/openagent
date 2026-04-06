const STORAGE_API_BASE = "openagent.apiBase";
export const SETTINGS_CHANGE_EVENT = "openagent-settings-change";

/**
 * HTTP API 基址：优先读 localStorage（Settings 页写入），否则 NEXT_PUBLIC_API_BASE，最后默认 8000。
 */
export function apiBase(): string {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(STORAGE_API_BASE)?.trim();
    if (stored) return stored.replace(/\/$/, "");
  }
  const env = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (env) return env.replace(/\/$/, "");
  return "http://127.0.0.1:8000";
}

export function setApiBase(url: string): void {
  if (typeof window === "undefined") return;
  const u = url.trim().replace(/\/$/, "");
  window.localStorage.setItem(STORAGE_API_BASE, u);
  window.dispatchEvent(new Event(SETTINGS_CHANGE_EVENT));
}

export function subscribeSettingsChange(cb: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const fn = () => cb();
  window.addEventListener(SETTINGS_CHANGE_EVENT, fn);
  return () => window.removeEventListener(SETTINGS_CHANGE_EVENT, fn);
}

/** 与 apiBase 同源的 WebSocket ``/ws`` 地址。 */
export function wsUrl(): string {
  const u = new URL(apiBase());
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.pathname = "/ws";
  u.search = "";
  u.hash = "";
  return u.toString();
}
