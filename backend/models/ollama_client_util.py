from __future__ import annotations

from urllib.parse import urlparse


def ollama_httpx_kwargs(host: str) -> dict[str, bool]:
    """
    本机 Ollama：禁用 httpx 读系统代理，避免 HTTP_PROXY 误伤 127.0.0.1 导致 502。
    远端 URL 仍保留默认 trust_env，便于需代理访问内网 Ollama 的场景。
    """
    parsed = urlparse(host if "://" in host else f"http://{host}")
    h = (parsed.hostname or "").lower()
    if h in ("127.0.0.1", "localhost", "::1"):
        return {"trust_env": False}
    return {}
