from __future__ import annotations

import os

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)

ALLOWED_ORIGINS_ENV = "OPENAGENT_ALLOWED_ORIGINS"


def _normalize_origin(origin: str) -> str:
    return origin.strip().rstrip("/")


def get_allowed_origins() -> list[str]:
    raw = os.environ.get(ALLOWED_ORIGINS_ENV)
    if raw is None:
        return list(DEFAULT_ALLOWED_ORIGINS)

    origins = [_normalize_origin(part) for part in raw.split(",")]
    return [origin for origin in origins if origin and origin != "*"]


def is_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    return _normalize_origin(origin) in set(get_allowed_origins())
