from __future__ import annotations

import os


_DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


def get_allowed_origins() -> list[str]:
    """Return trusted browser origins for HTTP CORS and WebSocket handshakes."""
    raw = os.getenv("OPENAGENT_ALLOWED_ORIGINS", "")
    if raw.strip():
        origins = [_normalize_origin(part) for part in raw.split(",")]
        return [origin for origin in origins if origin]
    return list(_DEFAULT_ALLOWED_ORIGINS)


def is_allowed_origin(origin: str | None) -> bool:
    """Allow non-browser clients without Origin; browser requests must be trusted."""
    if origin is None or not origin.strip():
        return True
    return _normalize_origin(origin) in set(get_allowed_origins())
