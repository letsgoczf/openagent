from __future__ import annotations

import os
from urllib.parse import urlsplit

ALLOWED_ORIGINS_ENV = "OPENAGENT_ALLOWED_ORIGINS"

DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
)


def _normalize_origin(origin: str) -> str:
    parsed = urlsplit(origin.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme.lower()}://{host}{port}"


def get_allowed_origins() -> list[str]:
    raw = os.environ.get(ALLOWED_ORIGINS_ENV, "")
    origins = raw.split(",") if raw.strip() else DEFAULT_ALLOWED_ORIGINS
    normalized = [_normalize_origin(origin) for origin in origins]
    return [origin for origin in normalized if origin]


def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    normalized = _normalize_origin(origin)
    return bool(normalized and normalized in set(get_allowed_origins()))
